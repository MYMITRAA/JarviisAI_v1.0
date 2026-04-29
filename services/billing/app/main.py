"""JarviisAI — Billing Service"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import logging, os, httpx
from app.core.logging_config import configure_logging

from app.services.billing_service import billing_service, PLANS
from app.core.metrics import setup_metrics

logging.basicConfig(level=os.getenv("LOG_LEVEL","info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.billing")

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL","http://auth-service:8001")
APP_URL = os.getenv("APP_URL","http://localhost:3000")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET","")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("💳 Billing Service ready")
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

app = FastAPI(title="JarviisAI Billing Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# ── Plans ────────────────────────────────────────────────────

@app.get("/api/v1/billing/plans")
async def list_plans():
    """Public endpoint — return all plan configurations."""
    return {
        name: {
            "name": p["name"],
            "price_monthly": p.get("price_monthly"),
            "price_yearly": p.get("price_yearly"),
            "limits": p["limits"],
        }
        for name, p in PLANS.items()
    }


# ── Checkout ──────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    org_id: str
    plan: str
    billing_period: str = "monthly"
    customer_email: Optional[str] = None


@app.post("/api/v1/billing/checkout")
async def create_checkout(data: CheckoutRequest):
    url = await billing_service.create_checkout_session(
        org_id=data.org_id,
        plan_name=data.plan,
        billing_period=data.billing_period,
        success_url=f"{APP_URL}/settings/billing?success=1",
        cancel_url=f"{APP_URL}/pricing",
        customer_email=data.customer_email,
    )
    return {"checkout_url": url}


@app.post("/api/v1/billing/portal")
async def customer_portal(org_id: str, stripe_customer_id: str):
    url = await billing_service.create_portal_session(
        stripe_customer_id=stripe_customer_id,
        return_url=f"{APP_URL}/settings/billing",
    )
    return {"portal_url": url}


# ── Subscription info ─────────────────────────────────────────

@app.get("/api/v1/billing/subscription/{stripe_subscription_id}")
async def get_subscription(stripe_subscription_id: str):
    sub = await billing_service.get_subscription(stripe_subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


@app.get("/api/v1/billing/invoices/{stripe_customer_id}")
async def list_invoices(stripe_customer_id: str):
    return await billing_service.list_invoices(stripe_customer_id)


@app.get("/api/v1/billing/upcoming/{stripe_customer_id}")
async def upcoming_invoice(stripe_customer_id: str):
    return await billing_service.get_upcoming_invoice(stripe_customer_id)


# ── Limit checking ────────────────────────────────────────────

@app.get("/api/v1/billing/check-limit")
async def check_limit(plan: str, resource: str, current_usage: int = 0):
    return billing_service.check_limit(plan, resource, current_usage)


# ── Stripe webhook ────────────────────────────────────────────

@app.post("/api/v1/billing/webhook")
async def stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
):
    """Receive and process Stripe webhook events."""
    body = await request.body()

    if STRIPE_WEBHOOK_SECRET and stripe_signature:
        event = billing_service.verify_webhook(body, stripe_signature, STRIPE_WEBHOOK_SECRET)
    else:
        import json
        event = json.loads(body)

    result = await billing_service.handle_webhook_event(event)

    # Propagate subscription changes to Auth service
    if result.get("org_id") and result.get("action") != "ignored":
        background_tasks.add_task(_update_org_plan, result)

    return {"received": True}


async def _update_org_plan(result: dict) -> None:
    """Notify Auth service of plan changes."""
    org_id = result.get("org_id")
    if not org_id:
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.patch(
                f"{AUTH_SERVICE_URL}/api/v1/internal/orgs/{org_id}/plan",
                json={
                    "plan": result.get("plan", "starter"),
                    "status": result.get("status", "active"),
                    "stripe_customer_id": result.get("stripe_customer_id"),
                    "stripe_subscription_id": result.get("stripe_subscription_id"),
                },
            )
    except Exception as e:
        logger.error(f"Failed to update org plan: {e}")
setup_metrics(app, service_name="billing")


