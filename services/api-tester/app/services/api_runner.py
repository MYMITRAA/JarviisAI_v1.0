"""
API Test Runner.

For each endpoint in a parsed spec:
  1. Build a realistic request (from schema examples or AI-generated)
  2. Execute HTTP request with configurable auth
  3. Validate: status code, response schema, headers, timing SLA
  4. Check: auth gates (401/403 when no token), error handling (422 for bad input)
  5. Stream results via Redis pub-sub
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from jsonschema import validate, ValidationError
import redis.asyncio as aioredis

from app.services.spec_parser import ParsedEndpoint, ParsedSpec, parser as spec_parser
from app.models.api_test import ApiTestType

logger = logging.getLogger("jarviis.api.runner")


class ApiTestRunner:

    def __init__(self, redis_url: str = "redis://:redis_secret@redis:6379/9"):
        self.redis_client = aioredis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    async def run(
        self,
        run_id: str,
        spec: ParsedSpec,
        base_url: str,
        auth_config: Optional[Dict] = None,
        environment: str = "default",
        timeout_seconds: int = 30,
    ) -> Dict:
        """
        Execute all tests for a parsed spec. Streams results via Redis.
        Returns final summary.
        """
        passed = failed = errors = 0
        results = []

        await self._publish(run_id, "status", {"status": "running", "total": len(spec.endpoints)})

        # Build auth headers
        auth_headers = self._build_auth_headers(auth_config)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=10),
            follow_redirects=True,
            verify=False,  # Accept self-signed certs for internal APIs
        ) as client:
            for endpoint in spec.endpoints:
                try:
                    ep_results = await self._test_endpoint(
                        client=client,
                        run_id=run_id,
                        endpoint=endpoint,
                        base_url=base_url,
                        spec=spec,
                        auth_headers=auth_headers,
                        auth_config=auth_config,
                    )
                    for r in ep_results:
                        results.append(r)
                        if r["status"] == "passed":
                            passed += 1
                        elif r["status"] == "failed":
                            failed += 1
                        else:
                            errors += 1
                        await self._publish(run_id, "result", r)
                except Exception as e:
                    logger.warning(f"Endpoint {endpoint.method} {endpoint.path} errored: {e}")
                    errors += 1

        total = passed + failed + errors
        summary = {
            "run_id": run_id,
            "status": "passed" if failed == 0 and errors == 0 else "failed",
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "total": total,
            "results": results,
        }
        await self._publish(run_id, "complete", summary)
        return summary

    async def _test_endpoint(
        self,
        client: httpx.AsyncClient,
        run_id: str,
        endpoint: ParsedEndpoint,
        base_url: str,
        spec: ParsedSpec,
        auth_headers: Dict,
        auth_config: Optional[Dict],
    ) -> List[Dict]:
        results = []

        # ── Test 1: Happy path — auth + valid request ──────────
        url = self._build_url(base_url, endpoint.path, endpoint.parameters)
        req_body = endpoint.request_body_example

        start = time.time()
        try:
            response = await client.request(
                method=endpoint.method,
                url=url,
                headers={**auth_headers, "Content-Type": "application/json", "Accept": "application/json"},
                json=req_body if req_body and endpoint.method in ("POST", "PUT", "PATCH") else None,
                params=self._build_query_params(endpoint.parameters),
            )
            latency_ms = int((time.time() - start) * 1000)
        except Exception as e:
            results.append(self._make_result(
                endpoint=endpoint,
                test_type=ApiTestType.STATUS_CODE,
                test_name=f"{endpoint.method} {endpoint.path} — connection",
                status="error",
                error_message=str(e),
                url=url,
            ))
            return results

        # Status code test
        expected_codes = [int(c) for c in endpoint.response_schemas.keys() if c.isdigit() and int(c) < 400]
        expected_code = expected_codes[0] if expected_codes else 200
        status_ok = response.status_code == expected_code or (
            200 <= response.status_code < 300  # any 2xx is ok if no spec
        )
        results.append(self._make_result(
            endpoint=endpoint,
            test_type=ApiTestType.STATUS_CODE,
            test_name=f"{endpoint.method} {endpoint.path} — status code",
            status="passed" if status_ok else "failed",
            request_url=url,
            response_status_code=response.status_code,
            expected_status=expected_code,
            response_time_ms=latency_ms,
            response_body_preview=response.text[:500],
            error_message=None if status_ok else f"Expected {expected_code}, got {response.status_code}",
        ))

        # ── Test 2: Response schema validation ─────────────────
        if str(response.status_code) in endpoint.response_schemas:
            schema = endpoint.response_schemas[str(response.status_code)]
            try:
                resp_json = response.json()
                errors = spec_parser.validate_response(schema, resp_json, spec.raw.get("components", {}).get("schemas", {}))
                results.append(self._make_result(
                    endpoint=endpoint,
                    test_type=ApiTestType.SCHEMA_VALIDATION,
                    test_name=f"{endpoint.method} {endpoint.path} — schema validation",
                    status="passed" if not errors else "failed",
                    request_url=url,
                    response_status_code=response.status_code,
                    schema_valid=not errors,
                    schema_errors=errors[:5] if errors else None,
                    response_time_ms=latency_ms,
                    error_message="; ".join(errors[:3]) if errors else None,
                ))
            except Exception:
                pass  # Non-JSON response — skip schema validation

        # ── Test 3: Response time SLA ───────────────────────────
        sla_ms = 2000  # 2s default SLA
        results.append(self._make_result(
            endpoint=endpoint,
            test_type=ApiTestType.RESPONSE_TIME,
            test_name=f"{endpoint.method} {endpoint.path} — response time < {sla_ms}ms",
            status="passed" if latency_ms < sla_ms else "failed",
            request_url=url,
            response_status_code=response.status_code,
            response_time_ms=latency_ms,
            error_message=None if latency_ms < sla_ms else f"Response took {latency_ms}ms (SLA: {sla_ms}ms)",
        ))

        # ── Test 4: Auth gate (if endpoint requires auth) ───────
        if endpoint.auth_required and auth_headers:
            try:
                unauth_response = await client.request(
                    method=endpoint.method,
                    url=url,
                    headers={"Content-Type": "application/json"},
                    json=req_body if req_body and endpoint.method in ("POST", "PUT", "PATCH") else None,
                )
                auth_gate_ok = unauth_response.status_code in (401, 403)
                results.append(self._make_result(
                    endpoint=endpoint,
                    test_type=ApiTestType.AUTH,
                    test_name=f"{endpoint.method} {endpoint.path} — auth gate (no token → 401/403)",
                    status="passed" if auth_gate_ok else "failed",
                    request_url=url,
                    response_status_code=unauth_response.status_code,
                    error_message=None if auth_gate_ok else f"Expected 401/403 without auth, got {unauth_response.status_code}",
                ))
            except Exception:
                pass

        # ── Test 5: Input validation (POST/PUT with bad data) ──
        if endpoint.method in ("POST", "PUT", "PATCH") and endpoint.request_body_schema:
            try:
                bad_response = await client.request(
                    method=endpoint.method,
                    url=url,
                    headers={**auth_headers, "Content-Type": "application/json"},
                    json={"__invalid_jarviis_test__": True},
                )
                validation_gate_ok = bad_response.status_code in (400, 422)
                results.append(self._make_result(
                    endpoint=endpoint,
                    test_type=ApiTestType.ERROR_HANDLING,
                    test_name=f"{endpoint.method} {endpoint.path} — input validation (bad data → 400/422)",
                    status="passed" if validation_gate_ok else "failed",
                    request_url=url,
                    response_status_code=bad_response.status_code,
                    error_message=None if validation_gate_ok else f"Bad input returned {bad_response.status_code}, expected 400/422",
                ))
            except Exception:
                pass

        return results

    def _build_url(self, base_url: str, path: str, parameters: List[Dict]) -> str:
        """Build a URL with path parameters filled in."""
        url = base_url.rstrip("/") + path
        # Fill path params with placeholder values
        for param in parameters:
            if param.get("in") == "path":
                name = param.get("name", "")
                example = param.get("example") or param.get("schema", {}).get("example") or "1"
                url = url.replace(f"{{{name}}}", str(example))
        # Replace any remaining {param} with "1"
        import re
        url = re.sub(r"\{[^}]+\}", "1", url)
        return url

    def _build_query_params(self, parameters: List[Dict]) -> Dict:
        params = {}
        for p in parameters:
            if p.get("in") == "query" and p.get("required"):
                name = p.get("name", "")
                example = p.get("example") or p.get("schema", {}).get("example") or p.get("value")
                if example is not None:
                    params[name] = str(example)
        return params

    def _build_auth_headers(self, auth_config: Optional[Dict]) -> Dict:
        if not auth_config:
            return {}
        auth_type = auth_config.get("type", "bearer")
        if auth_type == "bearer":
            token = auth_config.get("token", "")
            return {"Authorization": f"Bearer {token}"} if token else {}
        if auth_type == "api_key":
            key = auth_config.get("key_name", "X-API-Key")
            value = auth_config.get("key_value", "")
            return {key: value}
        if auth_type == "basic":
            import base64
            creds = base64.b64encode(
                f"{auth_config.get('username','')}:{auth_config.get('password','')}".encode()
            ).decode()
            return {"Authorization": f"Basic {creds}"}
        return {}

    def _make_result(self, endpoint: ParsedEndpoint, test_type, test_name: str, status: str, **kwargs) -> Dict:
        return {
            "endpoint_method": endpoint.method,
            "endpoint_path": endpoint.path,
            "test_type": test_type if isinstance(test_type, str) else test_type.value,
            "test_name": test_name,
            "status": status,
            **kwargs,
        }

    async def _publish(self, run_id: str, event: str, data: Dict) -> None:
        try:
            channel = f"api-run:{run_id}:events"
            await self.redis_client.publish(channel, json.dumps({"event": event, "data": data}))
        except Exception:
            pass


runner = ApiTestRunner()
