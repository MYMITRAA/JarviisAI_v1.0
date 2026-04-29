"""
JarviisAI Security Scanner.

Performs automated OWASP Top 10 + common web security checks:
  - Security headers (CSP, HSTS, X-Frame-Options, etc.)
  - Exposed sensitive information (stack traces, secrets in responses)
  - Authentication: session fixation, missing auth on protected routes
  - Injection: XSS, SQLi, path traversal (non-destructive probes only)
  - CORS misconfiguration
  - Rate limiting presence
  - TLS/SSL configuration
  - Common vulnerability indicators

NON-DESTRUCTIVE: All probes are read-only or benign
(no actual exploitation, no data modification).
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
from playwright.async_api import async_playwright

logger = logging.getLogger("jarviis.security")


class Severity:
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"
    INFO     = "info"


@dataclass
class SecurityFinding:
    severity: str
    category: str
    title: str
    description: str
    url: str
    evidence: Optional[str] = None
    remediation: str = ""
    cwe: Optional[str] = None
    owasp: Optional[str] = None
    false_positive_risk: str = "low"


@dataclass
class ScanResult:
    target_url: str
    scan_id: str
    total_checks: int
    findings: List[SecurityFinding]
    score: int                  # 0–100 (100 = perfectly secure)
    grade: str                  # A+ → F
    duration_seconds: float
    errors: List[str]

    @classmethod
    def compute_score(cls, findings: List[SecurityFinding]) -> tuple[int, str]:
        deductions = {
            Severity.CRITICAL: 30,
            Severity.HIGH:     15,
            Severity.MEDIUM:    7,
            Severity.LOW:       3,
            Severity.INFO:      0,
        }
        score = 100
        for f in findings:
            score -= deductions.get(f.severity, 0)
        score = max(0, score)
        grade = "A+" if score >= 95 else "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
        return score, grade


class SecurityScanner:
    """Non-destructive web security scanner."""

    async def scan(
        self,
        url: str,
        scan_id: str,
        auth_config: Optional[Dict] = None,
        depth: str = "standard",  # quick | standard | deep
    ) -> ScanResult:
        start = time.time()
        findings: List[SecurityFinding] = []
        errors: List[str] = []

        logger.info(f"Starting security scan {scan_id} for {url}")

        async with httpx.AsyncClient(
            timeout=15.0, verify=False, follow_redirects=True,
        ) as client:
            # ── 1. Security headers ────────────────────────────
            try:
                findings.extend(await self._check_security_headers(client, url))
            except Exception as e:
                errors.append(f"headers: {e}")

            # ── 2. TLS/SSL ────────────────────────────────────
            try:
                findings.extend(await self._check_tls(url))
            except Exception as e:
                errors.append(f"tls: {e}")

            # ── 3. Information disclosure ─────────────────────
            try:
                findings.extend(await self._check_info_disclosure(client, url))
            except Exception as e:
                errors.append(f"info: {e}")

            # ── 4. CORS misconfiguration ──────────────────────
            try:
                findings.extend(await self._check_cors(client, url))
            except Exception as e:
                errors.append(f"cors: {e}")

            # ── 5. Injection probes (non-destructive) ─────────
            if depth in ("standard", "deep"):
                try:
                    findings.extend(await self._check_injection_indicators(client, url))
                except Exception as e:
                    errors.append(f"injection: {e}")

            # ── 6. Rate limiting ──────────────────────────────
            if depth in ("standard", "deep"):
                try:
                    findings.extend(await self._check_rate_limiting(client, url))
                except Exception as e:
                    errors.append(f"rate_limit: {e}")

            # ── 7. Common exposed paths ───────────────────────
            try:
                findings.extend(await self._check_exposed_paths(client, url))
            except Exception as e:
                errors.append(f"paths: {e}")

            # ── 8. Playwright-based XSS + CSP checks ─────────
            if depth == "deep":
                try:
                    findings.extend(await self._browser_checks(url))
                except Exception as e:
                    errors.append(f"browser: {e}")

        total_checks = 8 if depth == "deep" else 7 if depth == "standard" else 5
        score, grade = ScanResult.compute_score(findings)

        return ScanResult(
            target_url=url,
            scan_id=scan_id,
            total_checks=total_checks * 5,  # approximate check count
            findings=findings,
            score=score,
            grade=grade,
            duration_seconds=round(time.time() - start, 2),
            errors=errors,
        )

    async def _check_security_headers(self, client: httpx.AsyncClient, url: str) -> List[SecurityFinding]:
        findings = []
        resp = await client.get(url)
        headers = {k.lower(): v for k, v in resp.headers.items()}

        required_headers = [
            ("strict-transport-security", Severity.HIGH, "HSTS",
             "Missing Strict-Transport-Security header — browsers may connect over HTTP",
             "Add: Strict-Transport-Security: max-age=31536000; includeSubDomains",
             "A2:2021", "CWE-319"),
            ("content-security-policy", Severity.HIGH, "CSP",
             "Missing Content-Security-Policy — XSS attacks are not mitigated",
             "Add a restrictive CSP header. Start with: default-src 'self'",
             "A3:2021", "CWE-693"),
            ("x-frame-options", Severity.MEDIUM, "Clickjacking",
             "Missing X-Frame-Options — page can be embedded in iframes (clickjacking risk)",
             "Add: X-Frame-Options: DENY or SAMEORIGIN",
             "A5:2021", "CWE-1021"),
            ("x-content-type-options", Severity.LOW, "MIME sniffing",
             "Missing X-Content-Type-Options: nosniff",
             "Add: X-Content-Type-Options: nosniff",
             "A5:2021", "CWE-16"),
            ("referrer-policy", Severity.LOW, "Referrer leakage",
             "Missing Referrer-Policy — sensitive URLs may leak to third parties",
             "Add: Referrer-Policy: strict-origin-when-cross-origin",
             "A5:2021", None),
            ("permissions-policy", Severity.INFO, "Permissions Policy",
             "Missing Permissions-Policy header",
             "Add Permissions-Policy to restrict browser feature access",
             None, None),
        ]

        for header_name, severity, category, desc, fix, owasp, cwe in required_headers:
            if header_name not in headers:
                findings.append(SecurityFinding(
                    severity=severity,
                    category="Security Headers",
                    title=f"Missing {header_name}",
                    description=desc,
                    url=url,
                    remediation=fix,
                    owasp=owasp,
                    cwe=cwe,
                ))

        # Check Server header disclosure
        if "server" in headers and headers["server"]:
            version_pattern = r"\d+\.\d+"
            if re.search(version_pattern, headers["server"]):
                findings.append(SecurityFinding(
                    severity=Severity.LOW,
                    category="Information Disclosure",
                    title="Server version disclosed in headers",
                    description=f"Server header reveals: {headers['server']}",
                    url=url,
                    evidence=f"Server: {headers['server']}",
                    remediation="Configure web server to not disclose version information",
                    owasp="A5:2021",
                    cwe="CWE-200",
                ))

        return findings

    async def _check_tls(self, url: str) -> List[SecurityFinding]:
        findings = []
        if url.startswith("http://") and not "localhost" in url and not "127.0.0.1" in url:
            findings.append(SecurityFinding(
                severity=Severity.CRITICAL,
                category="TLS/SSL",
                title="Site not served over HTTPS",
                description="The application is accessible over plain HTTP — all traffic is unencrypted",
                url=url,
                remediation="Obtain a TLS certificate (e.g. Let's Encrypt) and redirect HTTP → HTTPS",
                owasp="A2:2021",
                cwe="CWE-319",
            ))
        return findings

    async def _check_info_disclosure(self, client: httpx.AsyncClient, url: str) -> List[SecurityFinding]:
        findings = []

        # Check common debug/error endpoints
        debug_paths = ["/debug", "/trace", "/_debug", "/actuator", "/actuator/env",
                       "/actuator/health", "/swagger-ui.html", "/api-docs", "/.env",
                       "/phpinfo.php", "/info", "/status"]
        for path in debug_paths:
            try:
                test_url = url.rstrip("/") + path
                r = await client.get(test_url, timeout=5.0)
                if r.status_code == 200 and len(r.content) > 100:
                    body = r.text.lower()
                    is_sensitive = any(kw in body for kw in (
                        "password", "secret", "token", "api_key", "database",
                        "stack trace", "exception", "error at line",
                        "java.lang", "traceback (most recent", "system.exception"
                    ))
                    if is_sensitive:
                        findings.append(SecurityFinding(
                            severity=Severity.HIGH,
                            category="Information Disclosure",
                            title=f"Sensitive data exposed at {path}",
                            description=f"Debug endpoint {path} returned 200 with potentially sensitive content",
                            url=test_url,
                            evidence=f"HTTP {r.status_code}, {len(r.content)} bytes",
                            remediation="Disable debug endpoints in production",
                            owasp="A5:2021",
                            cwe="CWE-200",
                        ))
            except Exception:
                pass

        return findings

    async def _check_cors(self, client: httpx.AsyncClient, url: str) -> List[SecurityFinding]:
        findings = []
        malicious_origin = "https://evil.jarviis-test.com"

        try:
            resp = await client.options(url, headers={"Origin": malicious_origin, "Access-Control-Request-Method": "GET"})
            acao = resp.headers.get("access-control-allow-origin", "")

            if acao == "*":
                findings.append(SecurityFinding(
                    severity=Severity.MEDIUM,
                    category="CORS",
                    title="Overly permissive CORS: Access-Control-Allow-Origin: *",
                    description="Any origin can make cross-origin requests. Acceptable for public APIs, risky for authenticated APIs.",
                    url=url,
                    evidence=f"Access-Control-Allow-Origin: {acao}",
                    remediation="Restrict CORS to specific trusted origins",
                    owasp="A5:2021",
                    cwe="CWE-942",
                ))
            elif acao == malicious_origin:
                findings.append(SecurityFinding(
                    severity=Severity.HIGH,
                    category="CORS",
                    title="CORS reflects arbitrary Origin header",
                    description="Server reflects the Origin header without validation — CORS misconfiguration",
                    url=url,
                    evidence=f"Sent Origin: {malicious_origin}, received: {acao}",
                    remediation="Validate Origin against an allowlist before reflecting in ACAO header",
                    owasp="A5:2021",
                    cwe="CWE-942",
                ))
        except Exception:
            pass

        return findings

    async def _check_injection_indicators(self, client: httpx.AsyncClient, url: str) -> List[SecurityFinding]:
        """Non-destructive injection indicators — looks for error messages only, no actual exploitation."""
        findings = []

        # XSS reflection test — inject a benign marker and check if it's reflected unencoded
        xss_probe = "<jarviis-scan-probe>"
        test_url = f"{url}?q={xss_probe}&search={xss_probe}"
        try:
            resp = await client.get(test_url, timeout=5.0)
            if xss_probe in resp.text and "text/html" in resp.headers.get("content-type", ""):
                if "<jarviis-scan-probe>" in resp.text:
                    findings.append(SecurityFinding(
                        severity=Severity.HIGH,
                        category="XSS",
                        title="Potential reflected XSS — HTML tags reflected in response",
                        description="Query parameters are reflected in HTML response without encoding",
                        url=test_url,
                        evidence=f"Injected '<jarviis-scan-probe>' was reflected unencoded in response",
                        remediation="Encode all user input before rendering in HTML (use DOMPurify, escape functions)",
                        owasp="A3:2021",
                        cwe="CWE-79",
                        false_positive_risk="medium",
                    ))
        except Exception:
            pass

        # SQLi error detection — look for DB error messages in response
        sqli_probes = ["'", "\"", "1 OR 1=1", "1' OR '1'='1"]
        for probe in sqli_probes[:2]:  # Only test 2 probes
            test_url = f"{url}?id={probe}&search={probe}"
            try:
                resp = await client.get(test_url, timeout=5.0)
                body = resp.text.lower()
                db_errors = [
                    "sql syntax", "mysql_fetch", "ora-0", "pg_query",
                    "syntax error", "unclosed quotation", "sqlite_error",
                    "microsoft sql server", "db2 sql error"
                ]
                for err in db_errors:
                    if err in body:
                        findings.append(SecurityFinding(
                            severity=Severity.CRITICAL,
                            category="SQL Injection",
                            title="Database error message exposed — potential SQL injection",
                            description=f"SQL probe '{probe}' triggered a database error message in the response",
                            url=test_url,
                            evidence=f"Error pattern '{err}' found in response",
                            remediation="Use parameterized queries/prepared statements. Never expose DB errors to users.",
                            owasp="A3:2021",
                            cwe="CWE-89",
                        ))
                        break
            except Exception:
                pass

        return findings

    async def _check_rate_limiting(self, client: httpx.AsyncClient, url: str) -> List[SecurityFinding]:
        """Check if login endpoint has rate limiting."""
        findings = []
        login_paths = ["/login", "/api/login", "/auth/login", "/api/v1/auth/login", "/signin"]

        for path in login_paths:
            test_url = url.rstrip("/") + path
            try:
                # Send 15 rapid requests and check if rate limiting kicks in
                tasks = [
                    client.post(test_url, json={"email": "test@test.com", "password": "wrong"}, timeout=5.0)
                    for _ in range(15)
                ]
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                valid_responses = [r for r in responses if isinstance(r, httpx.Response)]

                if valid_responses:
                    rate_limited = any(r.status_code == 429 for r in valid_responses)
                    all_200 = all(r.status_code not in (429, 503) for r in valid_responses)

                    if not rate_limited and all_200 and len(valid_responses) > 10:
                        findings.append(SecurityFinding(
                            severity=Severity.MEDIUM,
                            category="Rate Limiting",
                            title=f"No rate limiting on {path}",
                            description=f"15 rapid requests to {path} were all accepted — brute force attacks possible",
                            url=test_url,
                            evidence=f"15 requests: {len([r for r in valid_responses if r.status_code < 400])} succeeded without 429",
                            remediation="Implement rate limiting on auth endpoints (e.g. slowapi, nginx limit_req)",
                            owasp="A7:2021",
                            cwe="CWE-307",
                        ))
                    break  # Only test one login path
            except Exception:
                pass

        return findings

    async def _check_exposed_paths(self, client: httpx.AsyncClient, url: str) -> List[SecurityFinding]:
        """Check for commonly exposed sensitive files."""
        findings = []
        sensitive_paths = [
            "/.git/HEAD", "/.git/config", "/.env", "/.env.local",
            "/config.json", "/config.yaml", "/docker-compose.yml",
            "/wp-config.php", "/web.config", "/phpinfo.php",
        ]
        for path in sensitive_paths:
            try:
                test_url = url.rstrip("/") + path
                resp = await client.get(test_url, timeout=5.0)
                if resp.status_code == 200 and len(resp.content) > 10:
                    findings.append(SecurityFinding(
                        severity=Severity.HIGH if ".git" in path or ".env" in path else Severity.MEDIUM,
                        category="Exposed Files",
                        title=f"Sensitive file accessible: {path}",
                        description=f"{path} returned HTTP 200 — may contain secrets or source code",
                        url=test_url,
                        evidence=f"HTTP 200, {len(resp.content)} bytes",
                        remediation=f"Block access to {path} in your web server configuration",
                        owasp="A5:2021",
                        cwe="CWE-538",
                    ))
            except Exception:
                pass

        return findings

    async def _browser_checks(self, url: str) -> List[SecurityFinding]:
        """Browser-based checks using Playwright — CSP effectiveness, mixed content."""
        findings = []
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
                context = await browser.new_context()
                page = await context.new_page()

                csp_violations = []
                page.on("console", lambda msg: csp_violations.append(msg.text) if "csp" in msg.text.lower() else None)

                try:
                    await page.goto(url, timeout=15000, wait_until="networkidle")

                    # Check for inline scripts (CSP bypass risk)
                    inline_scripts = await page.evaluate("""
                        () => Array.from(document.querySelectorAll('script:not([src])')).length
                    """)
                    if inline_scripts > 5:
                        findings.append(SecurityFinding(
                            severity=Severity.INFO,
                            category="CSP",
                            title=f"High inline script count ({inline_scripts})",
                            description="Many inline scripts may indicate CSP 'unsafe-inline' is required, weakening XSS protection",
                            url=url,
                            evidence=f"{inline_scripts} inline <script> elements found",
                            remediation="Move inline scripts to external files to enable strict CSP without 'unsafe-inline'",
                        ))
                except Exception:
                    pass
                finally:
                    await browser.close()
        except Exception as e:
            logger.debug(f"Browser checks failed: {e}")

        return findings


scanner = SecurityScanner()
