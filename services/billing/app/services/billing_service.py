"""
JarviisAI Billing Service.

Integrates with Stripe for subscription management:
  - Plan management: Starter / Pro / Team / Enterprise
  - Usage metering: test runs, deployments, API calls
  - Webhook handling: subscription events from Stripe
  - Plan limits enforcement: block over-quota operations
  - Invoice history and upcoming invoice preview
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import stripe
from fastapi import HTTPException

logger = logging.getLogger("jarviis.billing")

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")


# ── Plan definitions ─────────────────────────────────────────

PLANS = {
    "starter": {
        "name": "Starter",
        "price_monthly": 0,
        "price_yearly": 0,
        "stripe_price_id_monthly": os.getenv("STRIPE_STARTER_MONTHLY", ""),
        "stripe_price_id_yearly": os.getenv("STRIPE_STARTER_YEARLY", ""),
        "limits": {
            "test_runs_per_month": 100,
            "projects": 3,
            "team_members": 1,
            "environments": 1,
            "ai_test_generations": 20,
            "security_scans": 5,
            "deployments_per_month": 10,
            "api_testing": False,
            "cobol_testing": False,
            "sso": False,
            "priority_support": False,
        },
    },
    "pro": {
        "name": "Pro",
        "price_monthly": 49,
        "price_yearly": 470,
        "stripe_price_id_monthly": os.getenv("STRIPE_PRO_MONTHLY", ""),
        "stripe_price_id_yearly": os.getenv("STRIPE_PRO_YEARLY", ""),
        "limits": {
            "test_runs_per_month": 2000,
            "projects": 20,
            "team_members": 5,
            "environments": 5,
            "ai_test_generations": 500,
            "security_scans": 50,
            "deployments_per_month": 200,
            "api_testing": True,
            "cobol_testing": False,
            "sso": False,
            "priority_support": True,
        },
    },
    "team": {
        "name": "Team",
        "price_monthly": 149,
        "price_yearly": 1430,
        "stripe_price_id_monthly": os.getenv("STRIPE_TEAM_MONTHLY", ""),
        "stripe_price_id_yearly": os.getenv("STRIPE_TEAM_YEARLY", ""),
        "limits": {
            "test_runs_per_month": 10000,
            "projects": 100,
            "team_members": 25,
            "environments": 20,
            "ai_test_generations": 2000,
            "security_scans": 200,
            "deployments_per_month": 1000,
            "api_testing": True,
            "cobol_testing": True,
            "sso": False,
            "priority_support": True,
        },
    },
    "enterprise": {
        "name": "Enterprise",
        "price_monthly": None,  # Custom pricing
        "price_yearly": None,
        "stripe_price_id_monthly": os.getenv("STRIPE_ENTERPRISE_MONTHLY", ""),
        "limits": {
            "test_runs_per_month": -1,    # unlimited
            "projects": -1,
            "team_members": -1,
            "environments": -1,
            "ai_test_generations": -1,
            "security_scans": -1,
            "deployments_per_month": -1,
            "api_testing": True,
            "cobol_testing": True,
            "sso": True,
            "priority_support": True,
        },
    },
}


class BillingService:

    # ── Subscription management ───────────────────────────────

    async def create_checkout_session(
        self,
        org_id: str,
        plan_name: str,
        billing_period: str,  # "monthly" | "yearly"
        success_url: str,
        cancel_url: str,
        customer_email: Optional[str] = None,
    ) -> str:
        """Create a Stripe Checkout session. Returns the checkout URL."""
        if not stripe.api_key:
            raise HTTPException(status_code=503, detail="Stripe not configured")

        plan = PLANS.get(plan_name)
        if not plan:
            raise HTTPException(status_code=400, detail=f"Unknown plan: {plan_name}")

        price_key = f"stripe_price_id_{billing_period}"
        price_id = plan.get(price_key)
        if not price_id:
            raise HTTPException(status_code=400, detail=f"No Stripe price configured for {plan_name}/{billing_period}")

        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            customer_email=customer_email,
            metadata={"org_id": org_id, "plan": plan_name},
            subscription_data={
                "metadata": {"org_id": org_id, "plan": plan_name},
                "trial_period_days": 14 if plan_name in ("pro", "team") else None,
            },
        )
        return session.url

    async def create_portal_session(self, stripe_customer_id: str, return_url: str) -> str:
        """Create a Stripe Customer Portal session for self-serve billing management."""
        if not stripe.api_key:
            raise HTTPException(status_code=503, detail="Stripe not configured")

        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
        return session.url

    async def get_subscription(self, stripe_subscription_id: str) -> Optional[Dict]:
        """Fetch current subscription details from Stripe."""
        if not stripe.api_key or not stripe_subscription_id:
            return None
        try:
            sub = stripe.Subscription.retrieve(stripe_subscription_id)
            return {
                "id": sub.id,
                "status": sub.status,
                "current_period_start": datetime.fromtimestamp(sub.current_period_start, tz=timezone.utc).isoformat(),
                "current_period_end": datetime.fromtimestamp(sub.current_period_end, tz=timezone.utc).isoformat(),
                "cancel_at_period_end": sub.cancel_at_period_end,
                "plan": sub.metadata.get("plan", "starter"),
            }
        except Exception as e:
            logger.error(f"Stripe get_subscription error: {e}")
            return None

    async def cancel_subscription(self, stripe_subscription_id: str, at_period_end: bool = True) -> None:
        """Cancel a subscription (at end of period by default)."""
        if not stripe.api_key:
            raise HTTPException(status_code=503, detail="Stripe not configured")
        stripe.Subscription.modify(
            stripe_subscription_id,
            cancel_at_period_end=at_period_end,
        )

    async def get_upcoming_invoice(self, stripe_customer_id: str) -> Optional[Dict]:
        """Preview the next invoice."""
        if not stripe.api_key or not stripe_customer_id:
            return None
        try:
            invoice = stripe.Invoice.upcoming(customer=stripe_customer_id)
            return {
                "amount_due": invoice.amount_due / 100,
                "currency": invoice.currency.upper(),
                "period_start": datetime.fromtimestamp(invoice.period_start, tz=timezone.utc).isoformat(),
                "period_end": datetime.fromtimestamp(invoice.period_end, tz=timezone.utc).isoformat(),
                "lines": [
                    {
                        "description": item.description,
                        "amount": item.amount / 100,
                        "quantity": item.quantity,
                    }
                    for item in invoice.lines.data
                ],
            }
        except Exception:
            return None

    async def list_invoices(self, stripe_customer_id: str, limit: int = 10) -> List[Dict]:
        """List past invoices."""
        if not stripe.api_key or not stripe_customer_id:
            return []
        try:
            invoices = stripe.Invoice.list(customer=stripe_customer_id, limit=limit)
            return [
                {
                    "id": inv.id,
                    "number": inv.number,
                    "status": inv.status,
                    "amount_paid": inv.amount_paid / 100,
                    "currency": inv.currency.upper(),
                    "created": datetime.fromtimestamp(inv.created, tz=timezone.utc).isoformat(),
                    "pdf_url": inv.invoice_pdf,
                    "hosted_url": inv.hosted_invoice_url,
                }
                for inv in invoices.data
            ]
        except Exception as e:
            logger.error(f"Stripe list_invoices error: {e}")
            return []

    # ── Plan limits enforcement ───────────────────────────────

    def check_limit(self, plan_name: str, resource: str, current_usage: int) -> Dict:
        """Check if a resource limit would be exceeded."""
        plan = PLANS.get(plan_name, PLANS["starter"])
        limits = plan["limits"]
        limit = limits.get(resource)

        if limit is None:
            return {"allowed": True, "limit": None, "usage": current_usage, "unlimited": True}

        if isinstance(limit, bool):
            return {"allowed": limit, "limit": limit, "usage": None, "unlimited": False}

        if limit == -1:  # Unlimited
            return {"allowed": True, "limit": -1, "usage": current_usage, "unlimited": True}

        allowed = current_usage < limit
        return {
            "allowed": allowed,
            "limit": limit,
            "usage": current_usage,
            "remaining": max(0, limit - current_usage),
            "unlimited": False,
            "overage": max(0, current_usage - limit) if not allowed else 0,
        }

    def get_plan_features(self, plan_name: str) -> Dict:
        """Get full plan details."""
        plan = PLANS.get(plan_name, PLANS["starter"])
        return {
            "name": plan["name"],
            "price_monthly": plan.get("price_monthly"),
            "price_yearly": plan.get("price_yearly"),
            "limits": plan["limits"],
        }

    # ── Webhook handling ──────────────────────────────────────

    def verify_webhook(self, payload: bytes, sig_header: str, webhook_secret: str) -> Dict:
        """Verify and parse a Stripe webhook event."""
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
            return event
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    async def handle_webhook_event(self, event: Dict) -> Dict:
        """
        Process Stripe webhook events.
        Returns {org_id, action, plan, status} for the caller to update the DB.
        """
        event_type = event.get("type", "")
        data_obj = event.get("data", {}).get("object", {})

        if event_type == "checkout.session.completed":
            org_id = data_obj.get("metadata", {}).get("org_id")
            plan = data_obj.get("metadata", {}).get("plan", "pro")
            customer_id = data_obj.get("customer")
            subscription_id = data_obj.get("subscription")
            return {
                "org_id": org_id,
                "action": "subscription_created",
                "plan": plan,
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_id,
                "status": "active",
            }

        if event_type == "customer.subscription.updated":
            org_id = data_obj.get("metadata", {}).get("org_id")
            status = data_obj.get("status")
            plan = data_obj.get("metadata", {}).get("plan", "starter")
            return {
                "org_id": org_id,
                "action": "subscription_updated",
                "plan": plan if status == "active" else "starter",
                "stripe_subscription_id": data_obj.get("id"),
                "status": status,
            }

        if event_type in ("customer.subscription.deleted", "customer.subscription.paused"):
            org_id = data_obj.get("metadata", {}).get("org_id")
            return {
                "org_id": org_id,
                "action": "subscription_cancelled",
                "plan": "starter",
                "stripe_subscription_id": data_obj.get("id"),
                "status": "cancelled",
            }

        if event_type == "invoice.payment_failed":
            org_id = data_obj.get("subscription_details", {}).get("metadata", {}).get("org_id")
            return {
                "org_id": org_id,
                "action": "payment_failed",
                "status": "past_due",
            }

        return {"action": "ignored", "event_type": event_type}


billing_service = BillingService()
