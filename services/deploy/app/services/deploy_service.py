"""Deploy service — CRUD for servers, environments, deployments."""

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, update
from fastapi import HTTPException

from app.models.deployment import (
    DeployServer, DeployEnvironment, Deployment, RollbackSnapshot,
    DeploymentStatus, ServerProvider
)
from app.schemas.deployment import (
    ServerCreate, EnvironmentCreate, EnvironmentUpdate,
    DeploymentCreate, PromoteRequest
)
from app.services.docker.credentials import encrypt, decrypt, encrypt_dict


class DeployService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Servers ───────────────────────────────────────────────

    async def create_server(self, data: ServerCreate, org_id: str) -> DeployServer:
        server = DeployServer(
            org_id=org_id,
            name=data.name,
            host=data.host,
            port=data.port,
            ssh_user=data.ssh_user,
            deploy_path=data.deploy_path,
            provider=data.provider,
            tags=data.tags or {},
        )
        if data.ssh_private_key:
            server.ssh_private_key_enc = encrypt(data.ssh_private_key)

        self.db.add(server)
        await self.db.flush()
        return server

    async def list_servers(self, org_id: str) -> List[DeployServer]:
        result = await self.db.execute(
            select(DeployServer)
            .where(DeployServer.org_id == org_id, DeployServer.is_active == True)
            .order_by(DeployServer.name)
        )
        return list(result.scalars().all())

    async def get_server(self, server_id: str, org_id: str) -> Optional[DeployServer]:
        return await self.db.scalar(
            select(DeployServer)
            .where(DeployServer.id == server_id, DeployServer.org_id == org_id)
        )

    async def ping_server(self, server_id: str, org_id: str) -> dict:
        from app.services.ssh.ssh_executor import ssh_executor
        server = await self.get_server(server_id, org_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")

        key_pem = decrypt(server.ssh_private_key_enc) if server.ssh_private_key_enc else ""
        result = await ssh_executor.ping(server.host, server.port, server.ssh_user, key_pem)

        # Update last ping
        server.last_ping_at = datetime.now(timezone.utc)
        server.last_ping_ok = result["reachable"]
        if result.get("docker_version"):
            server.docker_version = result["docker_version"]
        await self.db.flush()

        return result

    # ── Environments ──────────────────────────────────────────

    async def create_environment(
        self, project_id: str, org_id: str, data: EnvironmentCreate
    ) -> DeployEnvironment:
        env = DeployEnvironment(
            org_id=org_id,
            project_id=project_id,
            name=data.name,
            tier=data.tier,
            server_id=data.server_id,
            deploy_path=data.deploy_path,
            compose_file=data.compose_file,
            strategy=data.strategy,
            health_check_url=data.health_check_url,
            requires_test_pass=data.requires_test_pass,
            auto_deploy_branch=data.auto_deploy_branch,
        )
        if data.env_vars:
            env.env_vars_enc = encrypt_dict(data.env_vars)

        self.db.add(env)
        await self.db.flush()
        return env

    async def list_environments(self, project_id: str, org_id: str) -> List[DeployEnvironment]:
        result = await self.db.execute(
            select(DeployEnvironment)
            .where(
                DeployEnvironment.project_id == project_id,
                DeployEnvironment.org_id == org_id,
                DeployEnvironment.is_active == True,
            )
            .order_by(DeployEnvironment.tier)
        )
        return list(result.scalars().all())

    async def get_environment(self, env_id: str, org_id: str) -> Optional[DeployEnvironment]:
        return await self.db.scalar(
            select(DeployEnvironment)
            .where(DeployEnvironment.id == env_id, DeployEnvironment.org_id == org_id)
        )

    async def update_environment(
        self, env_id: str, org_id: str, data: EnvironmentUpdate
    ) -> DeployEnvironment:
        env = await self.get_environment(env_id, org_id)
        if not env:
            raise HTTPException(status_code=404, detail="Environment not found")

        if data.server_id is not None: env.server_id = data.server_id
        if data.health_check_url is not None: env.health_check_url = data.health_check_url
        if data.strategy is not None: env.strategy = data.strategy
        if data.requires_test_pass is not None: env.requires_test_pass = data.requires_test_pass
        if data.auto_deploy_branch is not None: env.auto_deploy_branch = data.auto_deploy_branch
        if data.env_vars is not None: env.env_vars_enc = encrypt_dict(data.env_vars)

        await self.db.flush()
        return env

    # ── Deployments ───────────────────────────────────────────

    async def create_deployment(
        self, project_id: str, org_id: str, user_id: str, data: DeploymentCreate
    ) -> Deployment:
        env = await self.get_environment(data.environment_id, org_id)
        if not env:
            raise HTTPException(status_code=404, detail="Environment not found")

        # Save previous image for rollback
        previous_tag = env.current_image_tag

        deployment = Deployment(
            org_id=org_id,
            project_id=project_id,
            environment_id=data.environment_id,
            triggered_by=user_id,
            git_commit_sha=data.git_commit_sha,
            git_branch=data.git_branch,
            git_tag=data.git_tag,
            image_repository=data.image_repository,
            image_tag=data.image_tag or "latest",
            strategy=data.strategy or env.strategy,
            test_run_id=data.test_run_id,
            previous_image_tag=previous_tag,
            metadata=data.metadata or {},
        )
        self.db.add(deployment)
        await self.db.flush()
        return deployment

    async def get_deployment(self, deployment_id: str, org_id: str) -> Optional[Deployment]:
        return await self.db.scalar(
            select(Deployment)
            .where(Deployment.id == deployment_id, Deployment.org_id == org_id)
        )

    async def list_deployments(
        self,
        org_id: str,
        project_id: Optional[str] = None,
        environment_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Deployment], int]:
        q = select(Deployment).where(Deployment.org_id == org_id)
        if project_id:
            q = q.where(Deployment.project_id == project_id)
        if environment_id:
            q = q.where(Deployment.environment_id == environment_id)

        total = await self.db.scalar(select(func.count()).select_from(q.subquery())) or 0
        deps = (await self.db.execute(
            q.order_by(desc(Deployment.created_at))
             .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

        return list(deps), total

    async def get_stats(self, org_id: str) -> dict:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

        total = await self.db.scalar(
            select(func.count(Deployment.id)).where(Deployment.org_id == org_id)
        ) or 0

        today_count = await self.db.scalar(
            select(func.count(Deployment.id)).where(
                Deployment.org_id == org_id, Deployment.created_at >= today
            )
        ) or 0

        recent = await self.db.execute(
            select(
                func.count(Deployment.id).label("total"),
                func.count(Deployment.id).filter(Deployment.status == DeploymentStatus.RUNNING).label("success"),
                func.avg(Deployment.duration_seconds).label("avg_dur"),
            ).where(
                Deployment.org_id == org_id,
                Deployment.created_at >= seven_days_ago,
                Deployment.status.in_([DeploymentStatus.RUNNING, DeploymentStatus.FAILED]),
            )
        )
        row = recent.first()

        active = await self.db.scalar(
            select(func.count(Deployment.id)).where(
                Deployment.org_id == org_id,
                Deployment.status.in_([DeploymentStatus.BUILDING, DeploymentStatus.DEPLOYING, DeploymentStatus.PENDING]),
            )
        ) or 0

        env_count = await self.db.scalar(
            select(func.count(DeployEnvironment.id)).where(
                DeployEnvironment.org_id == org_id, DeployEnvironment.is_active == True
            )
        ) or 0

        success_rate = None
        if row and row.total and row.total > 0:
            success_rate = round((row.success or 0) / row.total * 100, 1)

        return {
            "total_deployments": total,
            "deployments_today": today_count,
            "success_rate_7d": success_rate,
            "avg_deploy_time_seconds": round(row.avg_dur, 1) if row and row.avg_dur else None,
            "active_deployments": active,
            "environments_count": env_count,
        }
