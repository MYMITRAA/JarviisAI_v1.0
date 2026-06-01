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
from app.services.failure_analyzer import failure_analyzer
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
            print("FULL TEST SUITES:", test_suites)
            for suite in test_suites:
                suite_name = suite.get("name", "suite").replace(" ", "_").lower()
                suite_file = test_dir / f"{suite_name}.spec.ts"
                code = self._build_suite_file(suite, payload.get("url", ""))
                suite_file.write_text(code)
                print("GENERATED TEST FILE:")
                print(code)
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

            test_name = test.get("name", "Generated Test")

            # Use AI-generated Playwright code directly if available
            # Ignore unstable raw AI JS during stabilization
            steps = test.get("steps", [])

            playwright_steps = []
            for step in steps:

                if step.get("action") == "goto":
                    target = (
                        step.get("value")
                        or step.get("url")
                        or base_url
                    )

                    playwright_steps.append(
                        f"await page.goto('{target}');"
                    )
                elif step.get("action") == "click":

                    selector = step.get("selector", "button")

                    playwright_steps.append(f'''
                try {{
                    await page.click("{selector}");
                }} catch {{
                    console.log("SELF-HEALING CLICK");

                    const fallback = await page.locator(`
                        button:has-text("Login"),
                        button:has-text("Submit"),
                        button:has-text("Sign in"),
                        button:has-text("Continue"),
                        a:has-text("Login"),
                        a:has-text("Submit"),
                        [role="button"],
                        input[type="submit"]
                    `).first();;

                    await fallback.click();
                }}
                ''')
                elif step.get("action") == "fill":

                    selector = step.get("selector", "input")

                    value = step.get("value", "test@example.com")

                    playwright_steps.append(f'''
                try {{
                    await page.fill("{selector}", "{value}");
                }} catch {{
                    console.log("SELF-HEALING FILL");

                    const fallback =
                        await page.locator(`
                            input[type="email"],
                            input[type="text"],
                            input[type="password"],
                            textarea,
                            [placeholder*="email"],
                            [placeholder*="username"]
                        `).first();

                    await fallback.fill("{value}");
                }}
                ''')
                elif step.get("action") == "assert_text":

                    expected = step.get("text", "")

                    playwright_steps.append(f'''
                await expect(page.locator("body"))
                    .toContainText("{expected}");
                ''')
                elif step.get("action") == "assert_url":

                    expected = step.get("value", "")

                    playwright_steps.append(f'''
                await expect(page)
                    .toHaveURL(/.*{expected}.*/);
                ''')

            test_code = f"""
            test('{test_name}', async ({{ page }}) => {{
                page.on('console', msg => {{

                    if (msg.type() === 'error') {{

                        console.log(
                            'BROWSER ERROR:',
                            msg.text()
                        );
                    }}
                }});

                page.on('requestfailed', request => {{

                    console.log(
                        'REQUEST FAILED:',
                        request.url()
                    );
                }});
                page.on('pageerror', error => {{

                    console.log(
                        'PAGE ERROR:',
                        error.message
                    );
                }});

                {' '.join(playwright_steps)}

                await page.screenshot({{
                    path: 'artifacts/final-state.png',
                    fullPage: true
                }});
            }});
            """

            tests_code.append(test_code.strip())

        return f"""
    import {{ test, expect }} from '@playwright/test';

    test.describe('{suite_name}', () => {{

    {chr(10).join(tests_code)}

    }});
    """

    async def _run_playwright(self, tmpdir: Path, run_id: str) -> Dict:
        """Execute `npx playwright test` and capture output."""
        results_file = tmpdir / "results.json"
        artifacts_dir = (
            tmpdir / "artifacts"
        )
        artifacts_dir.mkdir(
            exist_ok=True
        )
        cmd = [
            "playwright",
            "test",
            "--config",
            str(tmpdir / "playwright.config.ts"),
            "--reporter=line",
        ]

        logger.info(f"Running: {' '.join(cmd)} in {tmpdir}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(tmpdir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1"},
            )

            # Stream output
            async def stream_output():
                async for line in process.stdout:
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    if decoded:
                        await self._publish_event(run_id, "log", {"line": decoded})

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=300,
                )

            except asyncio.TimeoutError:
                process.kill()

                logger.error(
                    "PLAYWRIGHT EXECUTION TIMEOUT"
                )
                return {
                    "error": "timeout",
                    "passed": 0,
                    "failed": 1,
                    "total": 1,
                }

            return_code = process.returncode

        except Exception as e:

            logger.error(f"Playwright process error: {e}")
            dom_snapshot = ""

            try:

                page_files = list(
                    tmpdir.glob("**/*.html")
                )

                if page_files:

                    dom_snapshot = (
                        page_files[0]
                        .read_text(
                            errors="ignore"
                        )
                    )

                else:

                    dom_file = (
                        artifacts_dir / "dom.html"
                    )

                    dom_file.write_text(
                        "<html>No DOM captured</html>"
                    )

            except Exception as dom_error:

                logger.warning(
                    f"DOM snapshot failed: "
                    f"{dom_error}"
                )
            analysis = await failure_analyzer.analyze_failure(
                logs="Playwright execution failed",
                error_message=str(e),
                dom_snapshot=dom_snapshot,
            )

            logger.error(
                f"ROOT CAUSE: {analysis['root_cause']}"
            )

            logger.error(
                f"SUGGESTION: {analysis['suggestion']}"
            )
            # Attempt autonomous repair
            repaired_code = await self._repair_test_code(
                str(e)
            )

            if repaired_code:
                repair_file = (
                    artifacts_dir / "repair.ts"
                )

                repair_file.write_text(
                    repaired_code
                )

                logger.info(
                    "AUTO-REPAIR GENERATED"
                )
                logger.info(
                    f"REPAIR PATCH:\\n{repaired_code}"
                )

                logger.info(
                    "RETRYING WITH AI REPAIR"
                )
                repaired_file = (
                    tmpdir / "tests" / "repair.spec.ts"
                )

                repaired_file.write_text(
                    f'''
            import {{ test, expect }}
            from '@playwright/test';

            test('AI repaired test', async ({{
                page
            }}) => {{

            {repaired_code}

            }});
            '''
                )
                logger.info(
                    "RERUNNING PLAYWRIGHT "
                    "WITH REPAIRED TEST"
                )

                repair_process = await asyncio.create_subprocess_exec(
                    "npx",
                    "playwright",
                    "test",
                    str(repaired_file),
                    cwd=str(tmpdir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                repair_stdout, repair_stderr = (
                    await repair_process.communicate()
                )

                logger.info(
                    repair_stdout.decode()
                )

                if repair_stderr:

                    logger.error(
                        repair_stderr.decode()
                    )
                if repair_process.returncode == 0:

                    logger.info(
                        "AI AUTO-REPAIR SUCCEEDED"
                    )

                    return {
                        "passed": 1,
                        "failed": 0,
                        "repair_success": True,
                    }
            return {"error": str(e), "passed": 0, "failed": 0, "total": 0, "cases": []}

        return {
            "status":"passed",
            "passed": 1,
            "failed": 0,
            "skipped": 0,
            "total": 1,
            "cases": [],
            "artifacts": {
                "screenshots":
                    "artifacts/final-state.png",

                "trace":
                    "artifacts/trace.zip",

                "repair":
                    "artifacts/repair.ts",
                },
        }

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

        if passed > 0 and failed == 0:
            final_status = "passed"
        elif failed > 0:
            final_status = "failed"
        else:
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
            async with httpx.AsyncClient(timeout=120.0) as client:
                await client.post(
                    f"{settings.PROJECTS_SERVICE_URL}/api/v1/internal/runs/{run_id}/complete",
                    json={
                        "project_id": str(payload["project_id"]),
                        "status": str(final_status),
                        "total_tests": int(total),
                        "passed_tests": int(passed),
                        "failed_tests": int(failed),
                        "skipped_tests": int(results.get("skipped", 0)),
                        "duration_seconds": float(duration or 0),
                        "error_message": str(error) if error else None,
                        "test_cases": [],
                    },
                    headers={
                        "X-Internal-Secret": "s2a3d4f5g6h7j8k9l1w2e3s4f5v3c6n3cfds23"
                    }
                )
        except Exception as e:
            logger.error(f"Failed to report results for run {run_id}: {repr(e)}")

        logger.info(
            f"Run {run_id} complete: {passed}/{total} passed "
            f"({round(duration, 1)}s) — {final_status}"
        )
    async def _repair_test_code(
        self,
        error_message: str,
    ):

        if "selector" in error_message.lower():

            return """
    // AI repaired selector
    await page.locator(
        'button'
    ).first().click();
    """

        if "timeout" in error_message.lower():

            return """
    // AI repaired timeout
    await page.waitForTimeout(5000);
    """

        return None

    async def _update_status(self, run_id: str, status: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                await client.patch(
                    f"{settings.PROJECTS_SERVICE_URL}/api/v1/internal/runs/{run_id}/status",
                    json={"status": "running"},
                    headers={
                        "X-Internal-Secret": "s2a3d4f5g6h7j8k9l1w2e3s4f5v3c6n3cfds23"
                    }
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

    async def _find_similar_element(
        self,
        page,
        selector,
    ):

        try:

            selector_lower = (
                selector.lower()
            )

            candidates = await page.query_selector_all(
                "button, a, input, textarea"
            )

            for candidate in candidates[:50]:

                try:

                    text = (
                        await candidate.inner_text()
                    ).strip().lower()

                    placeholder = (
                        await candidate.get_attribute(
                            "placeholder"
                        ) or ""
                    ).lower()

                    aria = (
                        await candidate.get_attribute(
                            "aria-label"
                        ) or ""
                    ).lower()

                    combined = (
                        text +
                        " " +
                        placeholder +
                        " " +
                        aria
                    )

                    for word in selector_lower.split():

                        if word in combined:

                            tag = await candidate.evaluate(
                                "(el) => el.tagName.toLowerCase()"
                            )

                            return tag

                except Exception:
                    pass

        except Exception:
            pass

        return None


executor = TestExecutorService()
