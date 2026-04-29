"""
JarviisAI AGI Assistant.

Natural language interface over your entire testing and deployment data.
Users can ask questions like:
  - "Why are my tests failing today?"
  - "Which endpoints have the highest error rate?"
  - "Show me all deployments that broke production in the last 7 days"
  - "Generate a test plan for my checkout flow"
  - "What security issues did the last scan find?"

Claude uses tool calls to query internal APIs, then synthesizes the results
into a clear, actionable natural language response.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
import anthropic

logger = logging.getLogger("jarviis.assistant")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PROJECTS_SERVICE_URL = os.getenv("PROJECTS_SERVICE_URL", "http://projects:8002")
DEPLOY_SERVICE_URL = os.getenv("DEPLOY_SERVICE_URL", "http://deploy:8008")


# ── Tool definitions for Claude ────────────────────────────────

TOOLS = [
    {
        "name": "get_org_stats",
        "description": "Get high-level statistics for the organization: total projects, tests today, pass rate, active runs",
        "input_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string", "description": "The organization ID"}
            },
            "required": ["org_id"]
        }
    },
    {
        "name": "list_projects",
        "description": "List all projects in the org with their latest run status and pass rates",
        "input_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "limit": {"type": "integer", "default": 10}
            },
            "required": ["org_id"]
        }
    },
    {
        "name": "get_project_runs",
        "description": "Get recent test runs for a specific project",
        "input_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "project_id": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
                "status": {"type": "string", "description": "Filter by status: passed, failed, running, error"}
            },
            "required": ["org_id", "project_id"]
        }
    },
    {
        "name": "get_run_failures",
        "description": "Get failed test cases for a specific run with error details",
        "input_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "run_id": {"type": "string"}
            },
            "required": ["org_id", "run_id"]
        }
    },
    {
        "name": "get_deployments",
        "description": "Get recent deployments for a project or org",
        "input_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "project_id": {"type": "string", "description": "Optional — if omitted returns org-wide"},
                "limit": {"type": "integer", "default": 10},
                "status": {"type": "string", "description": "Filter: running, failed, rolled_back"}
            },
            "required": ["org_id"]
        }
    },
    {
        "name": "analyze_failure_patterns",
        "description": "Analyze patterns in test failures across multiple runs to identify root causes",
        "input_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "project_id": {"type": "string"},
                "days": {"type": "integer", "default": 7, "description": "Look back N days"}
            },
            "required": ["org_id", "project_id"]
        }
    },
]


class JarviisAssistant:
    """
    Agentic assistant — uses Claude with tool use to answer questions
    about your testing and deployment data.
    """

    def __init__(self):
        self._client = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if not self._client:
            self._client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        return self._client

    async def chat(
        self,
        message: str,
        org_id: str,
        conversation_history: List[Dict] = None,
        access_token: str = "",
    ) -> Dict:
        """
        Main chat entrypoint.
        Returns: {response: str, tool_calls: List, suggestions: List[str]}
        """
        if not ANTHROPIC_API_KEY:
            return {
                "response": "AI assistant is not configured — set ANTHROPIC_API_KEY to enable Jarviis.",
                "tool_calls": [],
                "suggestions": [],
            }

        history = conversation_history or []
        history.append({"role": "user", "content": message})

        client = self._get_client()

        # Initial Claude call with tools
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=self._system_prompt(org_id),
            tools=TOOLS,
            messages=history,
        )

        # Agentic loop — execute tool calls until stop_reason is "end_turn"
        tool_calls_made = []
        while response.stop_reason == "tool_use":
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            tool_results = []

            for tool_use in tool_uses:
                tool_name = tool_use.name
                tool_input = tool_use.input
                tool_calls_made.append({"tool": tool_name, "input": tool_input})

                # Execute the tool
                result = await self._execute_tool(tool_name, tool_input, org_id, access_token)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(result),
                })

            # Add assistant response + tool results to history
            history.append({"role": "assistant", "content": response.content})
            history.append({"role": "user", "content": tool_results})

            # Continue conversation
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=self._system_prompt(org_id),
                tools=TOOLS,
                messages=history,
            )

        # Extract final text response
        final_text = " ".join(
            block.text for block in response.content if hasattr(block, "text")
        ).strip()

        # Generate follow-up suggestions
        suggestions = self._generate_suggestions(message, final_text)

        return {
            "response": final_text,
            "tool_calls": tool_calls_made,
            "suggestions": suggestions,
        }

    async def _execute_tool(
        self, tool_name: str, tool_input: Dict, org_id: str, access_token: str
    ) -> Any:
        """Execute a tool call — queries internal APIs."""
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}

        async with httpx.AsyncClient(timeout=10.0) as client:
            if tool_name == "get_org_stats":
                r = await client.get(
                    f"{PROJECTS_SERVICE_URL}/api/v1/orgs/{org_id}/stats",
                    headers=headers
                )
                return r.json() if r.status_code == 200 else {"error": r.text}

            if tool_name == "list_projects":
                r = await client.get(
                    f"{PROJECTS_SERVICE_URL}/api/v1/orgs/{org_id}/projects",
                    params={"page_size": tool_input.get("limit", 10)},
                    headers=headers,
                )
                return r.json() if r.status_code == 200 else {"error": r.text}

            if tool_name == "get_project_runs":
                project_id = tool_input.get("project_id", "")
                params = {"page_size": tool_input.get("limit", 10)}
                if tool_input.get("status"):
                    params["status"] = tool_input["status"]
                r = await client.get(
                    f"{PROJECTS_SERVICE_URL}/api/v1/orgs/{org_id}/projects/{project_id}/runs",
                    params=params,
                    headers=headers,
                )
                return r.json() if r.status_code == 200 else {"error": r.text}

            if tool_name == "get_run_failures":
                run_id = tool_input.get("run_id", "")
                r = await client.get(
                    f"{PROJECTS_SERVICE_URL}/api/v1/orgs/{org_id}/runs/{run_id}/cases",
                    headers=headers,
                )
                if r.status_code == 200:
                    data = r.json()
                    failed = [c for c in data.get("cases", []) if c.get("status") == "failed"]
                    return {"failed_count": len(failed), "failures": failed[:20]}
                return {"error": r.text}

            if tool_name == "get_deployments":
                project_id = tool_input.get("project_id", "")
                url = (
                    f"{DEPLOY_SERVICE_URL}/api/v1/orgs/{org_id}/projects/{project_id}/deployments"
                    if project_id
                    else f"{DEPLOY_SERVICE_URL}/api/v1/orgs/{org_id}/deployments"
                )
                r = await client.get(url, params={"page_size": tool_input.get("limit", 10)}, headers=headers)
                return r.json() if r.status_code == 200 else {"error": r.text}

            if tool_name == "analyze_failure_patterns":
                project_id = tool_input.get("project_id", "")
                r = await client.get(
                    f"{PROJECTS_SERVICE_URL}/api/v1/orgs/{org_id}/projects/{project_id}/runs",
                    params={"page_size": 20, "status": "failed"},
                    headers=headers,
                )
                if r.status_code != 200:
                    return {"error": r.text}
                runs = r.json().get("runs", [])
                # Aggregate failure patterns
                pattern_counts: Dict[str, int] = {}
                for run in runs:
                    error = run.get("error_stage") or run.get("ai_summary", "")[:50]
                    if error:
                        pattern_counts[error] = pattern_counts.get(error, 0) + 1
                return {
                    "total_failed_runs": len(runs),
                    "common_failure_stages": sorted(pattern_counts.items(), key=lambda x: -x[1])[:5],
                    "recent_failures": runs[:5],
                }

        return {"error": f"Unknown tool: {tool_name}"}

    def _system_prompt(self, org_id: str) -> str:
        return f"""You are Jarviis — an expert AI assistant embedded in JarviisAI, an autonomous testing and deployment platform.

You help development teams understand their quality, testing, and deployment data.
You have access to tools that can query:
- Test runs: status, pass rates, failure patterns
- Deployments: history, rollbacks, environment status
- Security scans: findings, scores, trends

Current org_id: {org_id}

Your personality:
- Direct, technical, and actionable
- You give concrete numbers and specific recommendations
- You proactively notice patterns and flag issues
- You suggest next steps after every analysis
- Brief where possible, detailed when it matters

When answering:
1. Always use your tools to get real data before answering questions about state
2. Lead with the most important finding
3. End with 1-2 specific recommended actions
4. Use markdown formatting for clarity (bold for key numbers, bullet lists for findings)

You are not a generic chatbot — you are a QA and deployment expert with access to the user's real production data."""

    def _generate_suggestions(self, message: str, response: str) -> List[str]:
        """Generate contextual follow-up prompts."""
        msg_lower = message.lower()
        suggestions = []
        if "failing" in msg_lower or "fail" in msg_lower:
            suggestions.extend(["Show me the most common failure categories", "Which tests are flaky?"])
        if "deploy" in msg_lower:
            suggestions.extend(["Show recent rollbacks", "What's the average deploy time?"])
        if "security" in msg_lower:
            suggestions.extend(["Show me all critical findings", "What's my security score?"])
        if not suggestions:
            suggestions = [
                "What's my overall test health today?",
                "Show me failing tests from the last 7 days",
                "Which projects need attention?",
            ]
        return suggestions[:3]


assistant = JarviisAssistant()
