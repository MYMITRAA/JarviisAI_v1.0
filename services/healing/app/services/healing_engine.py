"""
HealingEngine — AI-powered test repair.

For each failed test case:
1. Classify failure type (selector_not_found | timeout | assertion | network | auth)
2. If selector_not_found → run SelectorRepairModel on live DOM
3. For assertion/logic failures → ask Claude to generate a patch
4. Apply fix, re-run the specific test
5. If still failing after MAX_ATTEMPTS → mark as "needs_human"
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential

from app.services.selector_repair import repair_model, RepairResult
from app.core.config import settings

logger = logging.getLogger("jarviis.healing.engine")


class FailureType:
    SELECTOR_NOT_FOUND = "selector_not_found"
    TIMEOUT            = "timeout"
    ASSERTION          = "assertion"
    NETWORK            = "network"
    AUTH               = "auth"
    UNKNOWN            = "unknown"


@dataclass
class HealingAttempt:
    test_name: str
    failure_type: str
    original_code: str
    healed_code: Optional[str]
    selector_changes: List[Dict]
    confidence: float
    strategy: str
    explanation: str
    success: bool


@dataclass
class HealingResult:
    run_id: str
    total_failed: int
    auto_healed: int
    needs_human: int
    healing_rate: float
    attempts: List[Dict]


class HealingEngine:

    def __init__(self):
        self._anthropic = None

    def _get_client(self):
        if not self._anthropic and settings.ANTHROPIC_API_KEY:
            import anthropic
            self._anthropic = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._anthropic

    async def heal_run(
        self,
        run_id: str,
        failed_cases: List[Dict],
        project_url: str,
        dom_snapshots: Optional[Dict[str, List]] = None,
    ) -> HealingResult:
        """
        Main entry point — heal all failed tests in a run.
        dom_snapshots: {page_url: [element_list]} — captured during re-crawl
        """
        logger.info(f"Starting healing for run {run_id}: {len(failed_cases)} failed tests")

        # Re-crawl to get fresh DOM (if no snapshot provided)
        if not dom_snapshots:
            dom_snapshots = await self._crawl_for_healing(project_url)

        attempts = []
        auto_healed = 0

        for case in failed_cases:
            attempt = await self._heal_one(case, dom_snapshots, project_url)
            attempts.append(asdict(attempt))
            if attempt.success:
                auto_healed += 1

        total = len(failed_cases)
        rate = round(auto_healed / total * 100, 1) if total > 0 else 0.0

        result = HealingResult(
            run_id=run_id,
            total_failed=total,
            auto_healed=auto_healed,
            needs_human=total - auto_healed,
            healing_rate=rate,
            attempts=attempts,
        )

        logger.info(f"Healing complete for run {run_id}: {auto_healed}/{total} healed ({rate}%)")
        return result

    async def _heal_one(
        self,
        case: Dict,
        dom_snapshots: Dict[str, List],
        project_url: str,
    ) -> HealingAttempt:
        """Attempt to heal a single failed test case."""
        test_name = case.get("name", "Unknown")
        error_msg = case.get("error_message", "")
        stack = case.get("stack_trace", "")
        test_code = case.get("test_code", "")
        page_url = case.get("page_url", project_url)

        failure_type = self._classify_failure(error_msg, stack)
        logger.debug(f"Healing '{test_name}': {failure_type}")

        if failure_type == FailureType.SELECTOR_NOT_FOUND:
            return await self._heal_selector(case, dom_snapshots.get(page_url, []))

        if failure_type in (FailureType.ASSERTION, FailureType.UNKNOWN):
            return await self._heal_with_ai(case, failure_type)

        # Timeout / network / auth — can't auto-heal these
        return HealingAttempt(
            test_name=test_name,
            failure_type=failure_type,
            original_code=test_code,
            healed_code=None,
            selector_changes=[],
            confidence=0.0,
            strategy="unheatable",
            explanation=f"{failure_type} failures require manual investigation.",
            success=False,
        )

    def _classify_failure(self, error_msg: str, stack: str) -> str:
        """Classify failure from error message patterns."""
        combined = f"{error_msg} {stack}".lower()
        if any(kw in combined for kw in ("locator.click", "locator.fill", "waiting for locator",
                                          "no element", "strict mode violation", "element not found",
                                          "unable to find", "nth(0) must resolve")):
            return FailureType.SELECTOR_NOT_FOUND
        if "timeout" in combined and "exceeded" in combined:
            return FailureType.TIMEOUT
        if any(kw in combined for kw in ("expect(", "tobevisible", "tohavetext",
                                          "tobe", "assertion", "expected")):
            return FailureType.ASSERTION
        if any(kw in combined for kw in ("net::err", "network", "econnrefused", "fetch failed")):
            return FailureType.NETWORK
        if any(kw in combined for kw in ("401", "403", "unauthorized", "forbidden", "login")):
            return FailureType.AUTH
        return FailureType.UNKNOWN

    async def _heal_selector(
        self, case: Dict, dom_elements: List[Dict]
    ) -> HealingAttempt:
        """Use SelectorRepairModel to find a replacement selector."""
        test_name = case.get("name", "")
        error_msg = case.get("error_message", "")
        test_code = case.get("test_code", "")

        # Extract broken selectors from error message and test code
        broken_selectors = self._extract_selectors(error_msg, test_code)
        if not broken_selectors:
            return HealingAttempt(
                test_name=test_name,
                failure_type=FailureType.SELECTOR_NOT_FOUND,
                original_code=test_code,
                healed_code=None,
                selector_changes=[],
                confidence=0.0,
                strategy="no_selector_extracted",
                explanation="Could not extract broken selector from error.",
                success=False,
            )

        healed_code = test_code
        changes = []
        overall_confidence = 1.0

        for broken in broken_selectors:
            result: RepairResult = repair_model.repair(
                broken_selector=broken,
                dom_snapshot=dom_elements,
                error_message=error_msg,
                similarity_threshold=settings.SIMILARITY_THRESHOLD,
            )

            if result.healed:
                healed_code = healed_code.replace(broken, result.repaired_selector)
                changes.append({
                    "broken": broken,
                    "repaired": result.repaired_selector,
                    "confidence": result.confidence,
                    "strategy": result.strategy,
                })
                overall_confidence = min(overall_confidence, result.confidence)

        success = len(changes) == len(broken_selectors) and bool(changes)

        return HealingAttempt(
            test_name=test_name,
            failure_type=FailureType.SELECTOR_NOT_FOUND,
            original_code=test_code,
            healed_code=healed_code if success else None,
            selector_changes=changes,
            confidence=overall_confidence if success else 0.0,
            strategy="selector_repair",
            explanation="\n".join(c.get("explanation", "") for c in changes) if changes
                        else "No replacement selector found with sufficient confidence.",
            success=success,
        )

    async def _heal_with_ai(self, case: Dict, failure_type: str) -> HealingAttempt:
        """Use Claude to understand the failure and generate a fixed test."""
        client = self._get_client()
        if not client:
            return HealingAttempt(
                test_name=case.get("name", ""),
                failure_type=failure_type,
                original_code=case.get("test_code", ""),
                healed_code=None,
                selector_changes=[],
                confidence=0.0,
                strategy="ai_unavailable",
                explanation="AI client not configured — set ANTHROPIC_API_KEY.",
                success=False,
            )

        test_code = case.get("test_code", "")
        error_msg = case.get("error_message", "")
        stack = case.get("stack_trace", "")

        prompt = f"""You are a Playwright test repair specialist.

A Playwright TypeScript test is failing. Analyze the failure and provide a fixed version.

## Original Test Code
```typescript
{test_code[:3000]}
```

## Error Message
{error_msg[:500]}

## Stack Trace
{stack[:800]}

## Instructions
1. Identify the root cause of the failure
2. Fix the test code minimally — change only what's necessary
3. Return a JSON object with this exact structure:
{{
  "explanation": "Brief explanation of what was wrong and what you fixed",
  "confidence": 0.0-1.0,
  "fixed_code": "complete fixed test code here",
  "changes": ["list of specific changes made"]
}}

Return ONLY the JSON object, no markdown, no explanation outside JSON."""

        try:
            response = await self._call_claude(client, prompt)
            data = json.loads(response.strip())
            fixed_code = data.get("fixed_code", "")
            confidence = float(data.get("confidence", 0.0))

            return HealingAttempt(
                test_name=case.get("name", ""),
                failure_type=failure_type,
                original_code=test_code,
                healed_code=fixed_code if confidence >= 0.7 else None,
                selector_changes=[],
                confidence=confidence,
                strategy="ai_repair",
                explanation=data.get("explanation", ""),
                success=confidence >= 0.7 and bool(fixed_code),
            )

        except Exception as e:
            logger.error(f"AI healing failed for {case.get('name')}: {e}")
            return HealingAttempt(
                test_name=case.get("name", ""),
                failure_type=failure_type,
                original_code=test_code,
                healed_code=None,
                selector_changes=[],
                confidence=0.0,
                strategy="ai_error",
                explanation=f"AI repair failed: {str(e)}",
                success=False,
            )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def _call_claude(self, client, prompt: str) -> str:
        response = await client.messages.create(
            model=settings.PRIMARY_MODEL,
            max_tokens=2048,
            temperature=0.1,
            system="You are a Playwright test repair specialist. Respond only with valid JSON.",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _extract_selectors(self, error_msg: str, test_code: str) -> List[str]:
        """Extract broken selectors from error messages and test code."""
        selectors = set()

        # From error: "Locator: locator('#broken-id')"
        for match in re.finditer(r"locator\(['\"](.+?)['\"]\)", error_msg, re.IGNORECASE):
            selectors.add(match.group(1))

        # From test code: page.locator(), page.click(), getByTestId etc.
        for match in re.finditer(
            r'\.(?:locator|click|fill|check|select)\([\'"]([^\'\"]+)[\'"]\)',
            test_code
        ):
            selectors.add(match.group(1))

        # From test code: getByTestId, getByLabel, getByPlaceholder
        for match in re.finditer(
            r'\.getBy(?:TestId|Label|Placeholder|Role|Text)\([\'"]([^\'\"]+)[\'"]\)',
            test_code
        ):
            selectors.add(match.group(1))

        return list(selectors)[:5]  # Cap at 5 selectors per test

    async def _crawl_for_healing(self, project_url: str) -> Dict[str, List]:
        """Quick DOM-only crawl to get fresh selectors."""
        try:
            from playwright.async_api import async_playwright
            snapshots: Dict[str, List] = {}

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
                context = await browser.new_context()
                page = await context.new_page()

                try:
                    await page.goto(project_url, timeout=15000, wait_until="networkidle")
                    elements = await page.evaluate("""() => {
                        return Array.from(document.querySelectorAll(
                            'button, input, select, textarea, a[href], [role]'
                        )).slice(0, 300).map(el => {
                            const r = el.getBoundingClientRect();
                            return {
                                tag: el.tagName.toLowerCase(),
                                id: el.id || null,
                                text: (el.textContent||'').trim().slice(0,80),
                                classes: Array.from(el.classList).slice(0,5),
                                attrs: {
                                    'aria-label': el.getAttribute('aria-label'),
                                    'placeholder': el.placeholder,
                                    'name': el.name,
                                    'role': el.getAttribute('role'),
                                    'type': el.type,
                                    'href': el.href,
                                },
                                selector: el.id ? '#'+el.id : el.tagName.toLowerCase(),
                                visible: r.width > 0 && r.height > 0,
                            };
                        }).filter(e => e.visible);
                    }""")
                    snapshots[project_url] = elements or []
                except Exception as e:
                    logger.warning(f"DOM crawl for healing failed: {e}")

                await browser.close()
            return snapshots

        except Exception as e:
            logger.error(f"Healing crawl error: {e}")
            return {}


healing_engine = HealingEngine()
