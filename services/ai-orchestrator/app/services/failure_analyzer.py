import logging
from typing import Dict

logger = logging.getLogger("jarviis.ai.failure")


class FailureAnalyzer:

    async def analyze_failure(
        self,
        logs: str,
        error_message: str,
        dom_snapshot: str = "",
    ) -> Dict:

        root_cause = "Unknown"

        suggestion = "Retry test"

        if "selector" in error_message.lower():

            root_cause = "Element selector changed"

            suggestion = (
                "Use stable selector "
                "or fallback locator"
            )
            if (
                "login" in dom_snapshot.lower()
                and "password" in dom_snapshot.lower()
            ):

                suggestion = (
                    "Detected login form "
                    "inside DOM snapshot"
                )

        elif "timeout" in error_message.lower():

            root_cause = "Page load timeout"

            suggestion = (
                "Increase timeout "
                "or wait for SPA hydration"
            )

        elif "navigation" in error_message.lower():

            root_cause = "Navigation failure"

            suggestion = (
                "Validate target URL "
                "and redirects"
            )

        logger.info(
            f"AI FAILURE ANALYSIS: {root_cause}"
        )

        return {
            "root_cause": root_cause,
            "suggestion": suggestion,
        }


failure_analyzer = FailureAnalyzer()