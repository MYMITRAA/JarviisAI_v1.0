"""
DeployOrchestrator — the brain of the Deploy Engine.

Pipeline for each deployment:
  PENDING → BUILDING (optional) → PUSHING (optional) → DEPLOYING → RUNNING

If any stage fails → FAILED → auto-trigger rollback if configured.
Streams live log events via Redis pub-sub for WebSocket.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.deployment import (
    Deployment, DeployEnvironment, DeployServer,
    RollbackSnapshot, DeploymentStatus, DeployStrategy
)
from app.services.ssh.ssh_executor import ssh_executor, DeployContext
from app.services.docker.credentials import decrypt, decrypt_dict, encrypt
from app.core.config import settings

logger = logging.getLogger("jarviis.deploy.orchestrator")

redis_client = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)


class DeployOrchestrator:

    async def run(self, deployment_id: str, db: AsyncSession) -> None:
        """
        Full deployment pipeline. Updates DB at each stage.
        Publishes real-time log events to Redis channel.
        """
        deployment = await db.get(Deployment, deployment_id)
        if not deployment:
            logger.error(f"Deployment {deployment_id} not found")
            return

        env = await db.get(DeployEnvironment, deployment.environment_id)
        if not env or not env.server_id:
            await self._fail(db, deployment, "No server configured for this environment", "config")
            return

        server = await db.get(DeployServer, env.server_id)
        if not server:
            await self._fail(db, deployment, "Server not found", "config")
            return

        # Test gate check
        if env.requires_test_pass and deployment.test_run_id:
            gate_pass = await self._check_test_gate(deployment.test_run_id)
            deployment.test_gate_passed = gate_pass
            if not gate_pass:
                await self._fail(
                    db, deployment,
                    "Test gate failed — deployment blocked. Fix test failures first.",
                    "test_gate"
                )
                await self._publish(deployment_id, "error", {
                    "message": "⛔ Deployment blocked: tests are failing",
                    "stage": "test_gate"
                })
                return

        # Take rollback snapshot of current state
        if server.ssh_private_key_enc:
            try:
                key_pem = decrypt(server.ssh_private_key_enc)
                snapshot_ctx = DeployContext(
                    deployment_id=deployment_id,
                    server_host=server.host,
                    server_port=server.port,
                    ssh_user=server.ssh_user,
                    ssh_private_key_pem=key_pem,
                    deploy_path=env.deploy_path,
                    compose_file=env.compose_file,
                    image_repository=deployment.image_repository or "",
                    image_tag=deployment.previous_image_tag or "latest",
                    env_vars={},
                )
                snapshot_data = await ssh_executor.take_snapshot(snapshot_ctx)
                snapshot = RollbackSnapshot(
                    deployment_id=deployment_id,
                    org_id=deployment.org_id,
                    project_id=deployment.project_id,
                    image_tag=deployment.previous_image_tag,
                    compose_content=snapshot_data.get("compose"),
                    running_containers=json.loads(snapshot_data.get("containers") or "{}") if snapshot_data.get("containers") else {},
                    expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                )
                db.add(snapshot)
                await db.flush()
            except Exception as e:
                logger.warning(f"Snapshot failed (non-fatal): {e}")

        # Update status to DEPLOYING
        deployment.status = DeploymentStatus.DEPLOYING
        deployment.started_at = datetime.now(timezone.utc)
        await db.flush()
        await self._publish(deployment_id, "stage_change", {"stage": "deploying", "message": "🚀 Deploy started"})

        # Decrypt env vars
        env_vars = {}
        if env.env_vars_enc:
            try:
                env_vars = decrypt_dict(env.env_vars_enc)
            except Exception:
                pass

        ctx = DeployContext(
            deployment_id=deployment_id,
            server_host=server.host,
            server_port=server.port,
            ssh_user=server.ssh_user,
            ssh_private_key_pem=decrypt(server.ssh_private_key_enc) if server.ssh_private_key_enc else "",
            deploy_path=env.deploy_path,
            compose_file=env.compose_file,
            image_repository=deployment.image_repository or "",
            image_tag=deployment.image_tag or "latest",
            env_vars=env_vars,
            strategy=deployment.strategy,
            health_check_url=env.health_check_url,
            health_check_timeout_s=env.health_check_timeout_s,
        )

        log_lines = []
        try:
            async for line in ssh_executor.deploy(ctx):
                log_lines.append(line)
                await self._publish(deployment_id, "log", {"line": line})

            # Success
            now = datetime.now(timezone.utc)
            deployment.status = DeploymentStatus.RUNNING
            deployment.completed_at = now
            deployment.duration_seconds = (now - deployment.started_at).total_seconds()
            deployment.deploy_log = "\n".join(log_lines)
            deployment.health_check_passed = True

            # Update environment state
            env.current_deployment_id = deployment_id
            env.current_image_tag = deployment.image_tag
            env.last_deployed_at = now

            await db.flush()
            await self._publish(deployment_id, "complete", {
                "status": "running",
                "message": "🎉 Deployment successful",
                "duration_seconds": deployment.duration_seconds,
            })

        except Exception as e:
            logger.error(f"Deploy {deployment_id} failed: {e}", exc_info=True)
            log_lines.append(f"ERROR: {e}")

            deployment.status = DeploymentStatus.FAILED
            deployment.completed_at = datetime.now(timezone.utc)
            deployment.error_message = str(e)
            deployment.deploy_log = "\n".join(log_lines)

            await db.flush()
            await self._publish(deployment_id, "error", {
                "status": "failed",
                "message": f"❌ Deploy failed: {e}",
            })

    async def rollback(
        self, deployment_id: str, db: AsyncSession, reason: str = ""
    ) -> Optional[Deployment]:
        """Roll back to the previous deployment for an environment."""
        deployment = await db.get(Deployment, deployment_id)
        if not deployment:
            raise ValueError(f"Deployment {deployment_id} not found")

        env = await db.get(DeployEnvironment, deployment.environment_id)
        if not env:
            raise ValueError("Environment not found")

        # Find the snapshot
        snapshot = deployment.rollback_snapshot
        if not snapshot or not snapshot.image_tag:
            raise ValueError("No rollback snapshot available for this deployment")

        # Create a new rollback deployment
        rollback_dep = Deployment(
            org_id=deployment.org_id,
            project_id=deployment.project_id,
            environment_id=deployment.environment_id,
            image_repository=deployment.image_repository,
            image_tag=snapshot.image_tag,
            git_branch=deployment.git_branch,
            strategy=DeployStrategy.RECREATE,  # Always recreate for rollbacks (fastest)
            is_rollback=True,
            previous_deployment_id=deployment_id,
            metadata={"rollback_reason": reason, "rolled_back_from": deployment_id},
        )
        db.add(rollback_dep)
        await db.flush()

        # Mark original as rolled back
        deployment.status = DeploymentStatus.ROLLED_BACK
        await db.flush()

        # Run async
        asyncio.create_task(self.run(rollback_dep.id, db))
        return rollback_dep

    async def promote(
        self,
        from_env_id: str,
        to_env_id: str,
        image_tag: Optional[str],
        db: AsyncSession,
        triggered_by: Optional[str] = None,
        run_tests: bool = True,
    ) -> Deployment:
        """Promote a deployment from one environment tier to another."""
        from_env = await db.get(DeployEnvironment, from_env_id)
        to_env = await db.get(DeployEnvironment, to_env_id)

        if not from_env or not to_env:
            raise ValueError("Source or target environment not found")

        # Use current image from source if not specified
        tag = image_tag or from_env.current_image_tag
        if not tag:
            raise ValueError("No image tag available from source environment")

        # Get the latest deployment from source for git context
        latest_src = await db.scalar(
            select(Deployment)
            .where(Deployment.environment_id == from_env_id)
            .order_by(desc(Deployment.created_at))
            .limit(1)
        )

        new_dep = Deployment(
            org_id=to_env.org_id,
            project_id=to_env.project_id,
            environment_id=to_env_id,
            image_repository=latest_src.image_repository if latest_src else None,
            image_tag=tag,
            git_commit_sha=latest_src.git_commit_sha if latest_src else None,
            git_branch=latest_src.git_branch if latest_src else None,
            strategy=to_env.strategy,
            triggered_by=triggered_by,
            metadata={
                "promoted_from": from_env_id,
                "promoted_from_tier": from_env.tier,
                "run_tests": run_tests,
            },
        )
        db.add(new_dep)
        await db.flush()

        asyncio.create_task(self.run(new_dep.id, db))
        return new_dep

    async def _check_test_gate(self, test_run_id: str) -> bool:
        """Check if the associated test run passed."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{settings.PROJECTS_SERVICE_URL}/api/v1/internal/runs/{test_run_id}/status"
                )
                if resp.status_code == 200:
                    return resp.json().get("status") == "passed"
        except Exception:
            pass
        return False

    async def _fail(
        self, db: AsyncSession, deployment: Deployment,
        message: str, stage: str
    ) -> None:
        deployment.status = DeploymentStatus.FAILED
        deployment.error_message = message
        deployment.error_stage = stage
        deployment.completed_at = datetime.now(timezone.utc)
        await db.flush()

    async def _publish(self, deployment_id: str, event: str, data: dict) -> None:
        try:
            channel = f"deploy:{deployment_id}:events"
            payload = json.dumps({"event": event, "data": data})
            await redis_client.publish(channel, payload)
        except Exception as e:
            logger.debug(f"Redis publish error: {e}")


orchestrator = DeployOrchestrator()
