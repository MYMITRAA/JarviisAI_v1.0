"""
JarviisAI — Test Executor Service

Receives generated test suites, executes them with Playwright,
streams real-time results via WebSocket/Redis pub-sub,
saves artifacts (screenshots, videos, traces), and reports results.
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
import httpx
import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger("jarviis.executor")

redis_client = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

# Playwright config template
PLAYWRIGHT_CONFIG = """
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: %(timeout)d,
  expect: { timeout: 10000 },
  fullyParallel: true,
  retries: 1,
  workers: %(workers)d,
  reporter: [
    ['json', { outputFile: 'results.json' }],
    ['list'],
  ],
  use: {
    headless: true,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
    viewport: { width: 1280, height: 720 },
    actionTimeout: 15000,
    navigationTimeout: 20000,
  },
  projects: [%(browser_configs)s],
});
"""

BROWSER_CONFIGS = {
    "chromium": "{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }",
    "firefox": "{ name: 'firefox', use: { ...devices['Desktop Firefox'] } }",
    "webkit": "{ name: 'webkit', use: { ...devices['Desktop Safari'] } }",
}


class TestExecutorService:

    async def execute(self, payload: Dict[str, Any]) -> None:
        """
        Full execution pipeline:
        1. Write test files to temp directory
        2. Run `npx playwright test`
        3. Parse results.json
        4. Stream individual test results via Redis pub-sub
        5. Report final results to Projects service
        """
        run_id = payload["run_id"]
        browsers = payload.get("browsers", ["chromium"])
        test_suites = payload.get("test_suites", [])

        logger.info(f"Executing run {run_id}: {sum(len(s.get('tests',[])) for s in test_suites)} tests")
        await self._update_status(run_id, "running")
        await self._publish_event(run_id, "status", {"status": "running", "stage": "executing"})

        with tempfile.TemporaryDirectory(prefix=f"jarviis-{run_id}-") as tmpdir:
            tmpdir = Path(tmpdir)

            # Write test files
            test_dir = tmpdir / "tests"
            test_dir.mkdir()

            total_written = 0
            for suite in test_suites:
                suite_name = suite.get("name", "suite").replace(" ", "_").lower()
                suite_file = test_dir / f"{suite_name}.spec.ts"
                code = self._build_suite_file(suite, payload.get("url", ""))
                suite_file.write_text(code)
                total_written += len(suite.get("tests", []))

            logger.info(f"Wrote {total_written} tests to {test_dir}")

            # Write playwright config
            browser_cfg = ", ".join(BROWSER_CONFIGS.get(b, BROWSER_CONFIGS["chromium"]) for b in browsers)
            config_content = PLAYWRIGHT_CONFIG % {
                "timeout": settings.TEST_TIMEOUT_MS,
                "workers": min(settings.MAX_PARALLEL_WORKERS, max(1, total_written // 5)),
                "browser_configs": browser_cfg,
            }
            (tmpdir / "playwright.config.ts").write_text(config_content)

            # Create minimal package.json
            (tmpdir / "package.json").write_text(json.dumps({
                "name": "jarviis-test-run",
                "version": "1.0.0",
                "scripts": {"test": "playwright test"},
                "devDependencies": {"@playwright/test": "^1.47.0"}
            }, indent=2))

            # Execute tests
            start_time = time.time()
            results = await self._run_playwright(tmpdir, run_id)
            duration = time.time() - start_time

            # Parse and report results
            await self._report_results(run_id, results, payload, duration)

    def _build_suite_file(self, suite: Dict, base_url: str) -> str:
        """Assemble a complete .spec.ts file from a test suite."""
        suite_name = suite.get("name", "Tests")
        tests_code = []

        for test in suite.get("tests", []):
            code = test.get("code", "")
            if not code:
                continue
            # Ensure imports aren't duplicated
            code = code.replace("import { test, expect } from '@playwright/test';", "").strip()
            tests_code.append(f"  // Priority: {test.get('priority', 'medium')}\n  {code}")

        return f"""import {{ test, expect }} from '@playwright/test';
// JarviisAI Generated Test Suite: {suite_name}
// Run ID: embedded

test.describe('{suite_name}', () => {{
{chr(10).join(tests_code)}
}});
"""

    async def _run_playwright(self, tmpdir: Path, run_id: str) -> Dict:
        """Execute `npx playwright test` and capture output."""
        results_file = tmpdir / "results.json"

        cmd = [
            "npx", "playwright", "test",
            "--config", str(tmpdir / "playwright.config.ts"),
            "--reporter", f"json:{results_file}",
        ]

        logger.info(f"Running: {' '.join(cmd)} in {tmpdir}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(tmpdir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1"},
            )

            # Stream output
            async def stream_output():
                async for line in process.stdout:
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    if decoded:
                        await self._publish_event(run_id, "log", {"line": decoded})

            await asyncio.gather(stream_output(), process.wait())
            return_code = process.returncode

        except Exception as e:
            logger.error(f"Playwright process error: {e}")
            return {"error": str(e), "passed": 0, "failed": 0, "total": 0, "cases": []}

        # Parse results.json
        if results_file.exists():
            try:
                data = json.loads(results_file.read_text())
                return self._parse_playwright_json(data)
            except Exception as e:
                logger.error(f"Failed to parse results.json: {e}")

        return {"error": "No results file", "passed": 0, "failed": 0, "total": 0, "cases": []}

    def _parse_playwright_json(self, data: Dict) -> Dict:
        """Parse Playwright's JSON reporter output."""
        cases = []
        passed = failed = skipped = 0

        for suite in data.get("suites", []):
            for spec in suite.get("specs", []):
                for result in spec.get("tests", []):
                    status = result.get("status", "failed")
                    duration_ms = result.get("duration", 0)
                    errors = result.get("errors", [])
                    error_msg = errors[0].get("message", "") if errors else None
                    stack = errors[0].get("stack", "") if errors else None

                    cases.append({
                        "name": spec.get("title", "Unknown"),
                        "file_path": spec.get("file", ""),
                        "status": "passed" if status == "expected" else "failed",
                        "duration_ms": duration_ms,
                        "error_message": error_msg,
                        "stack_trace": stack,
                        "retry_count": result.get("retry", 0),
                    })

                    if status == "expected":
                        passed += 1
                    elif status == "skipped":
                        skipped += 1
                    else:
                        failed += 1

        return {
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "total": passed + failed + skipped,
            "cases": cases,
        }

    async def _report_results(
        self, run_id: str, results: Dict, payload: Dict, duration: float
    ) -> None:
        """Send final results to Projects service."""
        passed = results.get("passed", 0)
        failed = results.get("failed", 0)
        total = results.get("total", 0)
        error = results.get("error")

        final_status = "passed" if failed == 0 and total > 0 else "failed"
        if error and total == 0:
            final_status = "error"

        # Publish completion event
        await self._publish_event(run_id, "complete", {
            "status": final_status,
            "passed": passed,
            "failed": failed,
            "total": total,
            "duration_seconds": round(duration, 2),
        })

        # Report to Projects service
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(
                    f"{settings.PROJECTS_SERVICE_URL}/api/v1/internal/runs/{run_id}/complete",
                    json={
                        "status": final_status,
                        "passed_tests": passed,
                        "failed_tests": failed,
                        "skipped_tests": results.get("skipped", 0),
                        "total_tests": total,
                        "duration_seconds": duration,
                        "error_message": error,
                        "test_cases": results.get("cases", []),
                    },
                )
        except Exception as e:
            logger.error(f"Failed to report results for run {run_id}: {e}")

        logger.info(
            f"Run {run_id} complete: {passed}/{total} passed "
            f"({round(duration, 1)}s) — {final_status}"
        )

    async def _update_status(self, run_id: str, status: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.patch(
                    f"{settings.PROJECTS_SERVICE_URL}/api/v1/internal/runs/{run_id}/status",
                    json={"status": status},
                )
        except Exception as e:
            logger.warning(f"Could not update status: {e}")

    async def _publish_event(self, run_id: str, event_type: str, data: Dict) -> None:
        """Publish real-time event to Redis pub-sub channel."""
        try:
            channel = f"run:{run_id}:events"
            message = json.dumps({"event": event_type, "data": data})
            await redis_client.publish(channel, message)
        except Exception as e:
            logger.debug(f"Redis publish error: {e}")


executor = TestExecutorService()
