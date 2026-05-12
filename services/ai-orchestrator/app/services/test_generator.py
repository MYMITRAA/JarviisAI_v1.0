"""
TestGenerationService — converts crawl results into executable Playwright tests.

Pipeline:
1. Receive crawl result from Crawler service
2. Build context-optimized prompt from app map
3. Call LLM (Claude primary, GPT-4o fallback)
4. Parse and validate generated test code
5. Send test suite to Test Executor
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from jinja2 import Template
import httpx

from app.services.llm_client import llm_client
from app.core.config import settings

logger = logging.getLogger("jarviis.ai.generator")

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "test_generation_v1.txt"

SYSTEM_PROMPT = """You are JarviisAI's autonomous test generation engine.
You are an expert senior QA architect. You generate production-quality Playwright TypeScript tests.
You always respond with valid JSON only — no markdown, no explanation text, no code fences.
Your tests are thoughtful, cover real user journeys, and use Playwright best practices."""


class TestGenerationService:

    async def generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point.
        payload: {run_id, project_id, org_id, url, project_type, browsers, crawl_result}
        Returns: {test_plan, test_suites, model_used, usage}
        """
        run_id = payload["run_id"]
        crawl_result = payload["crawl_result"]

        logger.info(f"Generating tests for run {run_id} — {crawl_result['pages_crawled']} pages")

        # Build prompt
        user_prompt = self._build_prompt(crawl_result, payload.get("url", ""))

        # Call LLM
        raw_text, model_used, usage = await llm_client.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=settings.MAX_TOKENS,
            temperature=0.2,
        )

        # Parse response
        result = self._parse_response(raw_text, run_id)

        logger.info(
            f"Generated {result['test_plan']['total_tests']} tests for run {run_id} "
            f"using {model_used}"
        )

        return {
            **result,
            "model_used": model_used,
            "usage": usage,
            "run_id": run_id,
        }

    def _build_prompt(self, crawl_result: Dict, url: str) -> str:
        """Build the LLM prompt from crawl data."""
        template_text = PROMPT_PATH.read_text()
        template = Template(template_text)

        # Trim to token budget
        pages = crawl_result.get("pages", [])[:settings.MAX_PAGES_IN_CONTEXT]
        for page in pages:
            if page.get("interactive_elements"):
                page["interactive_elements"] = page["interactive_elements"][:settings.MAX_ELEMENTS_PER_PAGE]

        context = crawl_result.get("app_context", {})

        return template.render(
            base_url=url or crawl_result.get("base_url", ""),
            app_framework=crawl_result.get("app_framework"),
            total_pages=crawl_result.get("pages_crawled", 0),
            has_auth=context.get("has_auth", False),
            has_forms=context.get("has_forms", False),
            has_checkout=context.get("has_checkout", False),
            pages=context.get("pages", pages[:settings.MAX_PAGES_IN_CONTEXT]),
            min_tests=5,
            max_tests=settings.MAX_TESTS_PER_RUN,
        )

    def _parse_response(self, raw_text: str, run_id: str) -> Dict:
        """Parse and validate the LLM JSON response."""
        # Strip any accidental markdown fences
        text = raw_text.strip()
        text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
        text = text.strip()

        # Extract JSON object if surrounded by noise
        json_match = re.search(r'\{[\s\S]+\}', text)
        if json_match:
            text = json_match.group(0)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error for run {run_id}: {e}\nRaw (first 500): {raw_text[:500]}")
            # Return a minimal valid structure
            return self._empty_result()

        # Validate structure
        if "test_suites" not in data or "test_plan" not in data:
            logger.warning(f"Unexpected AI response structure for run {run_id}")
            return self._empty_result()

        # Validate and fix test code
        for suite in data.get("test_suites", []):
            for test in suite.get("tests", []):
                code = test.get("code", "")
                if not self._is_valid_test_code(code):
                    test["code"] = self._fix_test_code(test)

        # Count total tests
        total = sum(len(s.get("tests", [])) for s in data.get("test_suites", []))
        data["test_plan"]["total_tests"] = total

        return data

    def _is_valid_test_code(self, code: str) -> bool:
        """Basic validation that the code looks like a Playwright test."""
        if not code:
            return False
        has_test = "test(" in code or "test.describe(" in code
        has_async = "async" in code
        has_expect = "expect" in code or "await" in code
        return has_test and has_async and has_expect

    def _fix_test_code(self, test: Dict) -> str:
        """Generate a minimal valid test if AI output is broken."""
        name = test.get("name", "Unknown test")
        desc = test.get("description", "")
        return f"""test('{name}', async ({{ page }}) => {{
  // {desc}
  // TODO: This test needs manual implementation
  test.setTimeout(30000);
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  // Add assertions here
}});"""

    def _empty_result(self) -> Dict:
        return {
            "test_plan": {
                "summary": "Test generation encountered an error",
                "total_tests": 0,
                "coverage_areas": [],
                "estimated_duration_seconds": 0,
            },
            "test_suites": [],
        }


class TestGenerationOrchestrator:
    """Coordinates generation → executor handoff."""

    def __init__(self):
        self.generator = TestGenerationService()

    async def run(self, payload: Dict[str, Any]) -> None:
        """Full pipeline: generate tests → send to executor."""
        run_id = payload["run_id"]

        # 1. Update status to GENERATING
        await self._update_run_status(run_id, "generating", stage="generating")

        try:
            result = await self.generator.generate(payload)

            # 2. Store crawl result and test plan on the run
            await self._store_test_plan(run_id, result)

            if result["test_plan"]["total_tests"] == 0:
                await self._update_run_status(
                    run_id, "error",
                    error="AI generated 0 tests. Check application URL and accessibility.",
                    stage="generate"
                )
                return

            # 3. Send to Test Executor
            await self._send_to_executor(payload, result)

        except Exception as e:
            logger.error(f"Generation failed for run {run_id}: {e}", exc_info=True)
            await self._update_run_status(run_id, "error", error=str(e), stage="generate")

    async def _store_test_plan(self, run_id: str, result: Dict) -> None:
        """Save the AI test plan to the run record."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.patch(
                    f"{settings.PROJECTS_SERVICE_URL}/api/v1/internal/runs/{run_id}/plan",
                    json={
                        "ai_test_plan": result["test_plan"],
                        "crawl_summary": {
                            "total_suites": len(result.get("test_suites", [])),
                            "total_tests": result["test_plan"]["total_tests"],
                            "coverage_areas": result["test_plan"].get("coverage_areas", []),
                            "model_used": result.get("model_used"),
                        },   
                    },
                    headers={
                        "x-internal-secret": settings.internal_service_secret
                    }
                )
        except Exception as e:
            import traceback

            logger.error(f"Could not store test plan: {e}")

            traceback.print_exc()

    async def _send_to_executor(self, payload: Dict, generation_result: Dict) -> None:
        """Send generated tests to the Test Executor service."""
        executor_payload = {
            "run_id": payload["run_id"],
            "project_id": payload["project_id"],
            "org_id": payload["org_id"],
            "url": payload["url"],
            "browsers": payload.get("browsers", ["chromium"]),
            "test_suites": generation_result["test_suites"],
            "test_plan": generation_result["test_plan"],
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{settings.TEST_EXECUTOR_URL}/api/v1/execute",
                    json=executor_payload,
                )
                if resp.status_code not in (200, 202):
                    raise RuntimeError(f"Executor rejected: {resp.status_code}")
        except Exception as e:
            logger.error(f"Failed to send to executor: {e}")
            await self._update_run_status(
                payload["run_id"], "error", error=str(e), stage="execute"
            )

    async def _update_run_status(
        self, run_id: str, status: str,
        error: Optional[str] = None, stage: Optional[str] = None
    ) -> None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.patch(
                    f"{settings.PROJECTS_SERVICE_URL}/api/v1/internal/runs/{run_id}/status",
                    json={"status": status, "error_message": error, "error_stage": stage},
                    headers={
                        "x-internal-secret": settings.internal_service_secret
                    }
                )
        except Exception as e:
            logger.warning(f"Could not update run status: {e}")


orchestrator = TestGenerationOrchestrator()
