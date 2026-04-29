"""JarviisAI — Enterprise SSO Service (SAML 2.0 + OIDC)"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse, Response
from pydantic import BaseModel
from typing import Optional, List
import json, logging, os, secrets, httpx

from app.services.saml_handler import saml_handler
from app.services.oidc_handler import oidc_handler
from app.core.config import settings
from app.core.metrics import setup_metrics
from app.core.logging_config import configure_logging
configure_logging(service_name="sso", level=os.getenv("LOG_LEVEL", "INFO"))

logging.basicConfig(level=os.getenv("LOG_LEVEL","info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.sso")

AUTH_SERVICE_URL = settings.AUTH_SERVICE_URL
APP_URL = settings.APP_URL


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔐 SSO Service ready (SAML 2.0 + OIDC)")
    yield


APP_URL = os.getenv("APP_URL", "http://localhost:3000")
INTERNAL_ORIGINS = [
    APP_URL,
    "http://localhost:3000",
    "http://jarviis-frontend:3000",
    "http://api-gateway:8000",
    "http://localhost:8000",
]


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
                headers = dict(message.get("headers", []))
                security_headers = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"x-xss-protection", b"1; mode=block"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
                ]
                existing = {h[0] for h in message.get("headers", [])}
                new_headers = list(message.get("headers", []))
                for h, v in security_headers:
                    if h not in existing:
                        new_headers.append((h, v))
                message = {**message, "headers": new_headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)

app = FastAPI(title="JarviisAI SSO Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# ── Provider management ───────────────────────────────────────

class ProviderCreate(BaseModel):
    org_id: str
    name: str
    protocol: str = "saml"
    # SAML
    idp_metadata_url: Optional[str] = None
    idp_entity_id: Optional[str] = None
    idp_sso_url: Optional[str] = None
    idp_certificate: Optional[str] = None
    # OIDC
    oidc_issuer: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_discovery_url: Optional[str] = None
    # Settings
    enforce_sso: bool = False
    auto_provision: bool = True
    allowed_domains: List[str] = []


setup_metrics(app, service_name="sso")


@app.get("/health")
async def health():
    return {"service": "sso", "status": "ok", "protocols": ["saml2", "oidc"]}


@app.post("/api/v1/sso/providers")
async def create_provider(data: ProviderCreate):
    """Configure SSO for an organization."""
    # If metadata URL provided for SAML, auto-fetch config
    if data.protocol == "saml" and data.idp_metadata_url:
        try:
            meta = await saml_handler.fetch_idp_metadata(data.idp_metadata_url)
            return {
                "message": "Provider configured from metadata",
                "detected": meta,
                "next_step": f"Upload SP metadata from: {settings.SSO_BASE_URL}/api/v1/sso/saml/{data.org_id}/metadata",
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not fetch IdP metadata: {e}")

    # If OIDC discovery URL provided, validate
    if data.protocol == "oidc" and data.oidc_discovery_url:
        try:
            doc = await oidc_handler.fetch_discovery(data.oidc_discovery_url)
            return {
                "message": "OIDC provider configured",
                "issuer": doc.get("issuer"),
                "authorization_endpoint": doc.get("authorization_endpoint"),
                "redirect_uri": f"{settings.SSO_BASE_URL}/api/v1/sso/oidc/{data.org_id}/callback",
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"OIDC discovery failed: {e}")

    return {"message": "Provider configuration accepted", "org_id": data.org_id}


# ── SAML SP Metadata ──────────────────────────────────────────

@app.get("/api/v1/sso/saml/{org_slug}/metadata")
async def saml_sp_metadata(org_slug: str):
    """Return SP metadata XML for upload to IdP."""
    sp_entity_id = f"{settings.SSO_BASE_URL}/saml/{org_slug}"
    acs_url = f"{settings.SSO_BASE_URL}/api/v1/sso/saml/{org_slug}/acs"
    slo_url = f"{settings.SSO_BASE_URL}/api/v1/sso/saml/{org_slug}/slo"

    metadata_xml = saml_handler.build_sp_metadata(
        sp_entity_id=sp_entity_id,
        acs_url=acs_url,
        slo_url=slo_url,
        certificate=settings.SAML_CERTIFICATE or None,
    )
    return Response(content=metadata_xml, media_type="application/xml")


# ── SAML SP-initiated SSO ─────────────────────────────────────

@app.get("/api/v1/sso/saml/{org_slug}/login")
async def saml_initiate(org_slug: str, return_to: str = "/dashboard"):
    """Initiate SAML SSO — redirect user to IdP."""
    # In production: look up provider config from DB
    # Using placeholder values for illustration
    idp_sso_url = f"https://idp.example.com/sso/{org_slug}"
    sp_entity_id = f"{settings.SSO_BASE_URL}/saml/{org_slug}"
    acs_url = f"{settings.SSO_BASE_URL}/api/v1/sso/saml/{org_slug}/acs"

    relay_state = return_to
    authn_url = saml_handler.build_authn_request(
        idp_sso_url=idp_sso_url,
        sp_entity_id=sp_entity_id,
        acs_url=acs_url,
        relay_state=relay_state,
    )
    return RedirectResponse(authn_url)


@app.post("/api/v1/sso/saml/{org_slug}/acs")
async def saml_acs(
    org_slug: str,
    SAMLResponse: str = Form(...),
    RelayState: str = Form(default="/dashboard"),
):
    """SAML Assertion Consumer Service — receive and validate IdP response."""
    result = saml_handler.parse_response(
        saml_response_b64=SAMLResponse,
        idp_certificate=None,  # Would be fetched from DB by org_slug
    )

    if not result.get("valid"):
        logger.warning(f"SAML login failed for {org_slug}: {result.get('error')}")
        return RedirectResponse(f"{APP_URL}/auth/login?error=sso_failed")

    email = result.get("email", "")
    if not email:
        return RedirectResponse(f"{APP_URL}/auth/login?error=no_email")

    # Provision user via Auth service
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            prov_resp = await client.post(
                f"{AUTH_SERVICE_URL}/api/v1/internal/sso/provision",
                json={
                    "email": email,
                    "given_name": result.get("given_name", ""),
                    "family_name": result.get("family_name", ""),
                    "org_slug": org_slug,
                    "provider": "saml",
                    "session_index": result.get("session_index", ""),
                },
            )
            if prov_resp.status_code not in (200, 201):
                logger.error(f"User provisioning failed: {prov_resp.text}")
                return RedirectResponse(f"{APP_URL}/auth/login?error=provision_failed")

            tokens = prov_resp.json()
            access_token = tokens.get("access_token", "")

    except Exception as e:
        logger.error(f"SSO provision error: {e}")
        return RedirectResponse(f"{APP_URL}/auth/login?error=server_error")

    # Redirect to app with token (React app picks this up)
    relay = RelayState or "/dashboard"
    return RedirectResponse(
        f"{APP_URL}/auth/sso-callback?access_token={access_token}&return_to={relay}"
    )


# ── OIDC flow ─────────────────────────────────────────────────

@app.get("/api/v1/sso/oidc/{org_slug}/login")
async def oidc_initiate(org_slug: str, return_to: str = "/dashboard"):
    """Initiate OIDC flow."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    # In production: fetch provider config from DB
    # Using discovery to build the URL
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?" + "&".join([
        f"client_id=PLACEHOLDER",
        f"redirect_uri={settings.SSO_BASE_URL}/api/v1/sso/oidc/{org_slug}/callback",
        "response_type=code",
        "scope=openid email profile",
        f"state={state}",
        f"nonce={nonce}",
    ])
    return RedirectResponse(auth_url)


@app.get("/api/v1/sso/oidc/{org_slug}/callback")
async def oidc_callback(org_slug: str, code: str, state: str):
    """OIDC callback — exchange code, validate token, provision user."""
    logger.info(f"OIDC callback for {org_slug}, code received")
    # Full implementation exchanges code, validates id_token, provisions user
    # Abbreviated here — same flow as SAML provision above
    return RedirectResponse(f"{APP_URL}/auth/login?error=oidc_not_configured")


# ── SSO settings validation ────────────────────────────────────

@app.post("/api/v1/sso/validate")
async def validate_provider(data: ProviderCreate):
    """Test SSO configuration without saving it."""
    if data.protocol == "saml":
        if data.idp_metadata_url:
            try:
                meta = await saml_handler.fetch_idp_metadata(data.idp_metadata_url)
                return {"valid": True, "detected": meta}
            except Exception as e:
                return {"valid": False, "error": str(e)}
        return {"valid": bool(data.idp_entity_id and data.idp_sso_url), "message": "Manual config accepted"}

    if data.protocol == "oidc":
        if data.oidc_discovery_url:
            try:
                doc = await oidc_handler.fetch_discovery(data.oidc_discovery_url)
                return {"valid": True, "issuer": doc.get("issuer"), "endpoints": {
                    "authorization": doc.get("authorization_endpoint"),
                    "token": doc.get("token_endpoint"),
                    "userinfo": doc.get("userinfo_endpoint"),
                    "jwks": doc.get("jwks_uri"),
                }}
            except Exception as e:
                return {"valid": False, "error": str(e)}

    return {"valid": False, "error": "Unknown protocol or missing required fields"}
