import os
"""JarviisAI API Gateway v1.1 — routes auth + projects"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import httpx, redis.asyncio as aioredis, logging, os
from app.core.logging_config import configure_logging
configure_logging(service_name="api-gateway", level=os.getenv("LOG_LEVEL", "INFO"))

logging.basicConfig(level=os.getenv("LOG_LEVEL","info").upper(), format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("jarviis.gateway")

AUTH = os.getenv("AUTH_SERVICE_URL","http://auth-service:8001")
PROJ = os.getenv("PROJECTS_SERVICE_URL","http://projects:8002")
REDIS_URL = os.getenv("REDIS_URL","redis://redis:6379/1")
ORIGINS = os.getenv("ALLOWED_ORIGINS","http://localhost:3000").split(",")

limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])
redis_client = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
http_client: httpx.AsyncClient = None

@asynccontextmanager
async def lifespan(app):
    global http_client
    http_client = httpx.AsyncClient(timeout=60.0)
    await redis_client.ping()
    logger.info("API Gateway ready")
    yield
    await http_client.aclose()
    await redis_client.close()



class SecurityHeadersMiddleware:
    """Add security headers to every response."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                new_headers = list(message.get("headers", []))
                existing = {h[0] for h in new_headers}
                for h, v in [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                ]:
                    if h not in existing:
                        new_headers.append((h, v))
                message = {**message, "headers": new_headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)

app = FastAPI(title="JarviisAI API Gateway", version="1.1.0", docs_url="/docs", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID"])

@app.get("/health")
async def health():
    return {"service": "api-gateway", "status": "ok"}

@app.api_route("/api/v1/auth/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
@limiter.limit("60/minute")
async def proxy_auth(request: Request, path: str):
    return await _proxy(request, f"{AUTH}/api/v1/auth/{path}")

@app.api_route("/api/v1/users/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_users(request: Request, path: str):
    return await _proxy(request, f"{AUTH}/api/v1/users/{path}")

@app.api_route("/api/v1/organizations/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_orgs(request: Request, path: str):
    return await _proxy(request, f"{AUTH}/api/v1/organizations/{path}")

@app.api_route("/api/v1/orgs/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_projects(request: Request, path: str):
    return await _proxy(request, f"{PROJ}/api/v1/orgs/{path}")

@app.api_route("/api/v1/webhooks/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_webhooks(request: Request, path: str):
    return await _proxy(request, f"{PROJ}/api/v1/webhooks/{path}")

async def _proxy(request: Request, upstream_url: str):
    """
    Proxy a request to an upstream service, preserving the response type.
    Handles JSON, streaming (CSV, ZIP, HTML), and binary responses correctly.
    """
    try:
        body = await request.body()
        import uuid as _uuid
        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length")
        }
        headers["X-Forwarded-For"] = request.client.host if request.client else ""
        # Propagate or generate trace/correlation ID
        if "x-request-id" not in {k.lower() for k in headers}:
            headers["X-Request-ID"] = str(_uuid.uuid4())
        if "x-trace-id" not in {k.lower() for k in headers}:
            headers["X-Trace-ID"] = headers.get("X-Request-ID", str(_uuid.uuid4()))

        # Stream the response so we can inspect content-type before buffering
        async with httpx.AsyncClient(timeout=60.0) as stream_client:
            upstream = await stream_client.request(
                method=request.method,
                url=upstream_url,
                headers=headers,
                content=body,
                params=dict(request.query_params),
            )

        content_type = upstream.headers.get("content-type", "application/json")

        # Streaming / binary responses — pass through as-is
        if any(ct in content_type for ct in ("text/csv", "application/zip",
                                              "application/octet-stream", "text/html",
                                              "application/pdf", "text/plain")):
            from fastapi.responses import Response
            return Response(
                content=upstream.content,
                status_code=upstream.status_code,
                media_type=content_type,
                headers={
                    "Content-Disposition": upstream.headers.get("Content-Disposition", ""),
                },
            )

        # JSON response
        try:
            resp_content = upstream.json()
        except Exception:
            resp_content = {"detail": upstream.text}

        response = JSONResponse(content=resp_content, status_code=upstream.status_code)
        # Echo request ID back so clients can correlate logs
        if "X-Request-ID" in headers:
            response.headers["X-Request-ID"] = headers["X-Request-ID"]
        return response

    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        raise HTTPException(status_code=500, detail="Gateway error")

DEPLOY = os.getenv("DEPLOY_SERVICE_URL","http://deploy:8008")

@app.api_route("/api/v1/deploy/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_deploy(request: Request, path: str):
    return await _proxy(request, f"{DEPLOY}/api/v1/{path}")

API_TESTER = os.getenv("API_TESTER_URL","http://api-tester:8009")
SECURITY = os.getenv("SECURITY_SERVICE_URL","http://security:8010")
JARVIIS_AI = os.getenv("JARVIIS_AI_URL","http://jarviis-ai:8012")

@app.api_route("/api/v1/api-tester/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_api_tester(request: Request, path: str):
    return await _proxy(request, f"{API_TESTER}/api/v1/{path}")

@app.api_route("/api/v1/security/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_security(request: Request, path: str):
    return await _proxy(request, f"{SECURITY}/api/v1/security/{path}")

@app.api_route("/api/v1/jarviis/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_jarviis_ai(request: Request, path: str):
    return await _proxy(request, f"{JARVIIS_AI}/api/v1/{path}")

COBOL_SVC = os.getenv("COBOL_SERVICE_URL","http://cobol:8013")
BILLING_SVC = os.getenv("BILLING_SERVICE_URL","http://billing:8014")

@app.api_route("/api/v1/cobol/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_cobol(request: Request, path: str):
    return await _proxy(request, f"{COBOL_SVC}/api/v1/cobol/{path}")

@app.api_route("/api/v1/billing/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_billing(request: Request, path: str):
    return await _proxy(request, f"{BILLING_SVC}/api/v1/billing/{path}")

SSO_SVC = os.getenv("SSO_SERVICE_URL","http://sso:8015")
MOBILE_SVC = os.getenv("MOBILE_SERVICE_URL","http://mobile:8016")

@app.api_route("/api/v1/sso/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_sso(request: Request, path: str):
    return await _proxy(request, f"{SSO_SVC}/api/v1/sso/{path}")

@app.api_route("/api/v1/mobile/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_mobile(request: Request, path: str):
    return await _proxy(request, f"{MOBILE_SVC}/api/v1/mobile/{path}")

# ── SaaS Platform Services ────────────────────────────────────
EVENTS_SVC      = os.getenv("EVENTS_SERVICE_URL",      "http://events:8017")
USAGE_SVC       = os.getenv("USAGE_SERVICE_URL",        "http://usage:8018")
NOTIF_SVC       = os.getenv("NOTIFICATIONS_SERVICE_URL","http://notifications:8019")
ANALYTICS_SVC   = os.getenv("ANALYTICS_SERVICE_URL",   "http://analytics:8020")
REPORTS_SVC     = os.getenv("REPORTS_SERVICE_URL",      "http://reports:8021")
FLAGS_SVC       = os.getenv("FLAGS_SERVICE_URL",        "http://feature-flags:8022")
AUDIT_SVC       = os.getenv("AUDIT_SERVICE_URL",        "http://audit:8023")
SEARCH_SVC      = os.getenv("SEARCH_SERVICE_URL",       "http://search:8024")
COMPLIANCE_SVC  = os.getenv("COMPLIANCE_SERVICE_URL",   "http://compliance:8025")
HEALTH_SVC      = os.getenv("HEALTH_SERVICE_URL",       "http://health-scoring:8026")

@app.api_route("/api/v1/events/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_events(request: Request, path: str):
    return await _proxy(request, f"{EVENTS_SVC}/api/v1/events/{path}")

@app.api_route("/api/v1/usage/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_usage(request: Request, path: str):
    return await _proxy(request, f"{USAGE_SVC}/api/v1/usage/{path}")

@app.api_route("/api/v1/notifications/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_notifications(request: Request, path: str):
    return await _proxy(request, f"{NOTIF_SVC}/api/v1/notifications/{path}")

@app.api_route("/api/v1/analytics/{path:path}", methods=["GET","POST"])
async def proxy_analytics(request: Request, path: str):
    return await _proxy(request, f"{ANALYTICS_SVC}/api/v1/analytics/{path}")

@app.api_route("/api/v1/reports/{path:path}", methods=["GET","POST"])
async def proxy_reports(request: Request, path: str):
    return await _proxy(request, f"{REPORTS_SVC}/api/v1/reports/{path}")

@app.api_route("/api/v1/flags/{path:path}", methods=["GET","POST","DELETE"])
async def proxy_flags(request: Request, path: str):
    return await _proxy(request, f"{FLAGS_SVC}/api/v1/flags/{path}")

@app.api_route("/api/v1/audit/{path:path}", methods=["GET","POST"])
async def proxy_audit(request: Request, path: str):
    return await _proxy(request, f"{AUDIT_SVC}/api/v1/audit/{path}")

@app.api_route("/api/v1/search/{path:path}", methods=["GET"])
async def proxy_search(request: Request, path: str):
    return await _proxy(request, f"{SEARCH_SVC}/api/v1/search/{path}")

@app.api_route("/api/v1/search", methods=["GET"])
async def proxy_search_root(request: Request):
    return await _proxy(request, f"{SEARCH_SVC}/api/v1/search")

@app.api_route("/api/v1/compliance/{path:path}", methods=["GET","POST","DELETE"])
async def proxy_compliance(request: Request, path: str):
    return await _proxy(request, f"{COMPLIANCE_SVC}/api/v1/compliance/{path}")

@app.api_route("/api/v1/health-score/{path:path}", methods=["GET"])
async def proxy_health_score(request: Request, path: str):
    return await _proxy(request, f"{HEALTH_SVC}/api/v1/health-score/{path}")

# ── Missing service routes ────────────────────────────────────
HEALING_SVC = os.getenv("HEALING_SERVICE_URL", "http://healing:8006")
VISUAL_SVC  = os.getenv("VISUAL_SERVICE_URL",  "http://visual:8007")

@app.api_route("/api/v1/heal/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_healing(request: Request, path: str):
    return await _proxy(request, f"{HEALING_SVC}/api/v1/heal/{path}")

@app.api_route("/api/v1/visual/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def proxy_visual(request: Request, path: str):
    return await _proxy(request, f"{VISUAL_SVC}/api/v1/visual/{path}")

@app.api_route("/api/v1/orgs/{org_id}/export", methods=["GET"])
async def proxy_org_export(request: Request, org_id: str):
    return await _proxy(request, f"{PROJ}/api/v1/orgs/{org_id}/export")
