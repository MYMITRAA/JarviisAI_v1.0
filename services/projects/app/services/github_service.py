"""
GitHub Webhook Handler.
Receives push/PR events, verifies HMAC signature, triggers test runs.
Also handles posting status checks back to GitHub.
"""

import hashlib
import hmac
import httpx
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.project import GitHubIntegration, TestRun, TriggerType, TestRunStatus
from app.services.project_service import ProjectService
from app.schemas.project import TestRunCreate

logger = logging.getLogger("jarviis.github")

GITHUB_API = "https://api.github.com"


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub HMAC-SHA256 webhook signature."""
    if not settings.GITHUB_WEBHOOK_SECRET:
        logger.warning("GITHUB_WEBHOOK_SECRET not set — skipping signature verification")
        return True

    expected = "sha256=" + hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


class GitHubWebhookService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.project_svc = ProjectService(db)

    async def handle_push(self, payload: dict) -> Optional[TestRun]:
        print("HANDLE_PUSH_STARTED")
        """Handle GitHub push event — trigger test run if integration active."""
        repo_full_name = payload.get("repository", {}).get("full_name")
        ref = payload.get("ref", "")
        commit_sha = payload.get("after", "")
        print("REPO:", repo_full_name)
        print("REF:", ref)
        print("COMMIT:", commit_sha)
        head_commit = payload.get("head_commit") or {}

        if not repo_full_name or commit_sha == "0000000000000000000000000000000000000000":
            return None  # Branch deleted or empty push

        branch = ref.replace("refs/heads/", "")

        integration = await self.project_svc.get_integration_by_repo(repo_full_name)
        print("INTEGRATION FOUND:", integration)
        if not integration or not integration.trigger_on_push:
            print("NO INTEGRATION OR PUSH DISABLED")
            return None

        # Branch filter check
        if integration.branch_filter and branch not in integration.branch_filter.split(","):
            logger.info(f"Branch {branch} not in filter — skipping")
            print("BRANCH FILTER BLOCKED")
            return None
        print("CREATING RUN NOW")
        run = await self.project_svc.create_run(
            project_id=integration.project_id,
            org_id=integration.org_id,
            user_id=None,
            data=TestRunCreate(
                project_id=integration.project_id,
                trigger_type=TriggerType.GITHUB_PUSH,
                git_branch=branch,
                git_commit_sha=commit_sha,
                metadata={
                    "github_ref": ref,
                    "commit_message": head_commit.get("message", ""),
                    "author": head_commit.get("author", {}).get("name", ""),
                },
            ),
        )
        print("RUN CREATED:", run.id)

        # Update integration last_webhook_at
        from datetime import datetime, timezone
        integration.last_webhook_at = datetime.now(timezone.utc)
        await self.db.flush()

        # Post pending status to GitHub
        await self._post_commit_status(
            integration=integration,
            commit_sha=commit_sha,
            state="pending",
            description="JarviisAI tests queued...",
            run_id=run.id,
        )

        # Kick off pipeline
        await self.project_svc.trigger_run_pipeline(run.id)

        logger.info(f"Push event: triggered run {run.id} for {repo_full_name} @ {branch}")
        return run

    async def handle_pull_request(self, payload: dict) -> Optional[TestRun]:
        """Handle GitHub pull_request event — trigger test run on open/synchronize."""
        action = payload.get("action")
        if action not in ("opened", "synchronize", "reopened"):
            return None

        pr = payload.get("pull_request", {})
        repo_full_name = payload.get("repository", {}).get("full_name")
        pr_number = payload.get("number")
        commit_sha = pr.get("head", {}).get("sha", "")
        branch = pr.get("head", {}).get("ref", "")

        integration = await self.project_svc.get_integration_by_repo(repo_full_name)
        if not integration or not integration.trigger_on_pr:
            return None

        run = await self.project_svc.create_run(
            project_id=integration.project_id,
            org_id=integration.org_id,
            user_id=None,
            data=TestRunCreate(
                project_id=integration.project_id,
                trigger_type=TriggerType.GITHUB_PR,
                git_branch=branch,
                git_commit_sha=commit_sha,
                git_pr_number=pr_number,
                metadata={
                    "pr_title": pr.get("title", ""),
                    "pr_author": pr.get("user", {}).get("login", ""),
                    "pr_action": action,
                },
            ),
        )

        integration.last_webhook_at = datetime.now(timezone.utc)
        await self.db.flush()

        await self._post_commit_status(
            integration=integration,
            commit_sha=commit_sha,
            state="pending",
            description="JarviisAI tests queued...",
            run_id=run.id,
        )

        await self.project_svc.trigger_run_pipeline(run.id)

        logger.info(f"PR event: triggered run {run.id} for {repo_full_name} PR #{pr_number}")
        return run

    async def post_run_result(self, run: TestRun, integration: GitHubIntegration) -> None:
        """Post final test results back to GitHub as commit status."""
        if not run.git_commit_sha or not integration:
            return

        if run.status == TestRunStatus.PASSED:
            state = "success"
            desc = f"All {run.total_tests} tests passed in {run.duration_display}"
        elif run.status == TestRunStatus.FAILED:
            state = "failure"
            desc = f"{run.failed_tests}/{run.total_tests} tests failed"
        else:
            state = "error"
            desc = f"Test run {run.status}: {run.error_message or 'Unknown error'}"

        await self._post_commit_status(
            integration=integration,
            commit_sha=run.git_commit_sha,
            state=state,
            description=desc,
            run_id=run.id,
        )

        # Post PR comment with details if this was a PR run
        if run.git_pr_number and integration.repo_owner and integration.repo_name:
            await self._post_pr_comment(run, integration)

    async def _post_commit_status(
        self,
        integration: GitHubIntegration,
        commit_sha: str,
        state: str,
        description: str,
        run_id: str,
    ) -> None:
        """Post commit status check to GitHub."""
        if not settings.GITHUB_APP_ID or not integration.installation_id:
            logger.debug("GitHub App not configured — skipping status post")
            return

        token = await self._get_installation_token(integration.installation_id)
        if not token:
            return

        url = f"{GITHUB_API}/repos/{integration.repo_full_name}/statuses/{commit_sha}"
        payload = {
            "state": state,
            "target_url": f"https://app.jarviis.ai/runs/{run_id}",
            "description": description[:139],  # GitHub limit
            "context": "jarviis-ai/tests",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
                )
                if resp.status_code not in (200, 201):
                    logger.warning(f"GitHub status post failed: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.error(f"GitHub API error posting status: {e}")

    async def _post_pr_comment(self, run: TestRun, integration: GitHubIntegration) -> None:
        """Post a detailed PR comment with test results."""
        token = await self._get_installation_token(integration.installation_id)
        if not token:
            return

        emoji = "✅" if run.status == TestRunStatus.PASSED else "❌"
        body = f"""{emoji} **JarviisAI Test Results** — {run.status.upper()}

| Metric | Value |
|--------|-------|
| Total Tests | {run.total_tests} |
| ✅ Passed | {run.passed_tests} |
| ❌ Failed | {run.failed_tests} |
| Pass Rate | {run.pass_rate or 0}% |
| Duration | {run.duration_display} |
| Branch | `{run.git_branch or "unknown"}` |

{f"**AI Summary:** {run.ai_summary}" if run.ai_summary else ""}

[View full report →](https://app.jarviis.ai/runs/{run.id})
"""
        url = f"{GITHUB_API}/repos/{integration.repo_full_name}/issues/{run.git_pr_number}/comments"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    url,
                    json={"body": body},
                    headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
                )
        except Exception as e:
            logger.error(f"GitHub PR comment error: {e}")

    async def _get_installation_token(self, installation_id: str) -> Optional[str]:
        """Get a GitHub App installation access token (stub for now — full JWT impl in Phase 2)."""
        logger.debug(f"Getting token for installation {installation_id}")
        return None  # Will implement with full GitHub App JWT auth in next sprint
