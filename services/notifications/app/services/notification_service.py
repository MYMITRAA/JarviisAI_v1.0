"""
JarviisAI Notifications Service.

Consumes events from the event bus and delivers notifications via:
  - Email (SMTP — existing infrastructure)
  - Slack (incoming webhooks)
  - Microsoft Teams (incoming webhooks)
  - Custom webhooks (HTTP POST to user-configured URLs)
  - In-app notifications (stored in Redis, polled by frontend)

Each org configures their notification preferences:
  - Which events trigger notifications
  - Which channels receive them
  - Per-project overrides

Event → Notification mapping:
  test.failed          → Slack + Email (immediate)
  test.completed       → Slack (if configured)
  deploy.rolled_back   → Slack + Email + PagerDuty
  security.issue_critical → Email + Slack (always)
  usage.warning_80pct  → Email (account owner)
  usage.limit_reached  → Email + In-app banner
  billing.trial_expired → Email + In-app banner
  billing.payment_failed → Email (urgent)
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
import httpx
import redis.asyncio as aioredis

logger = logging.getLogger("jarviis.notifications")

REDIS_URL = os.getenv("REDIS_URL", "redis://:redis_secret@redis:6379/17")
EVENTS_SERVICE_URL = os.getenv("EVENTS_SERVICE_URL", "http://events:8017")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@jarviis.ai")
APP_URL = os.getenv("APP_URL", "https://jarviis.ai")

# In-app notifications TTL (7 days)
NOTIF_TTL = 7 * 24 * 3600

# Default event → channel config
DEFAULT_CONFIG = {
    "test.failed":            {"channels": ["slack", "in_app"], "urgent": False},
    "test.completed":         {"channels": ["in_app"], "urgent": False},
    "deploy.rolled_back":     {"channels": ["slack", "email", "in_app"], "urgent": True},
    "deploy.failed":          {"channels": ["slack", "in_app"], "urgent": False},
    "security.issue_critical":{"channels": ["slack", "email", "in_app"], "urgent": True},
    "usage.warning_80pct":    {"channels": ["email", "in_app"], "urgent": False},
    "usage.limit_reached":    {"channels": ["email", "in_app"], "urgent": True},
    "billing.trial_expired":  {"channels": ["email", "in_app"], "urgent": True},
    "billing.payment_failed": {"channels": ["email", "in_app"], "urgent": True},
    "billing.plan_changed":   {"channels": ["email", "in_app"], "urgent": False},
    "healing.applied":        {"channels": ["in_app"], "urgent": False},
}


class NotificationService:

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self):
        self._redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

    async def disconnect(self):
        if self._redis:
            await self._redis.aclose()

    async def handle_event(self, event_type: str, org_id: str, payload: dict) -> None:
        """Route an event to the appropriate notification channels."""
        config = DEFAULT_CONFIG.get(event_type, {})
        if not config:
            return  # No notifications for this event type

        channels = config.get("channels", [])
        message = self._format_message(event_type, payload)

        # Get org notification settings from Redis
        org_config = await self._get_org_config(org_id)

        tasks = []
        for channel in channels:
            if channel == "in_app":
                tasks.append(self._send_in_app(org_id, event_type, message, payload))
            elif channel == "slack":
                slack_url = org_config.get("slack_webhook_url")
                if slack_url:
                    tasks.append(self._send_slack(slack_url, event_type, message, payload))
            elif channel == "email":
                email = org_config.get("notification_email")
                if email:
                    tasks.append(self._send_email(email, event_type, message, payload))
            elif channel == "teams":
                teams_url = org_config.get("teams_webhook_url")
                if teams_url:
                    tasks.append(self._send_teams(teams_url, message, payload))

        # Custom webhooks
        custom_webhooks = org_config.get("custom_webhooks", [])
        for webhook_url in custom_webhooks:
            tasks.append(self._send_webhook(webhook_url, event_type, payload))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def save_org_config(self, org_id: str, config: dict) -> None:
        """Save org notification preferences to Redis."""
        if self._redis:
            await self._redis.set(
                f"notif:config:{org_id}",
                json.dumps(config),
                ex=86400 * 365,
            )

    async def get_in_app_notifications(self, org_id: str, limit: int = 50) -> List[dict]:
        """Get in-app notification feed for an org."""
        if not self._redis:
            return []
        key = f"notif:inbox:{org_id}"
        items = await self._redis.lrange(key, 0, limit - 1)
        return [json.loads(item) for item in items]

    async def mark_read(self, org_id: str, notification_id: str) -> None:
        """Mark a notification as read."""
        if self._redis:
            await self._redis.sadd(f"notif:read:{org_id}", notification_id)

    async def get_unread_count(self, org_id: str) -> int:
        """Get unread notification count."""
        if not self._redis:
            return 0
        total = await self._redis.llen(f"notif:inbox:{org_id}")
        read = await self._redis.scard(f"notif:read:{org_id}")
        return max(0, total - read)

    # ── Channel senders ───────────────────────────────────────

    async def _send_in_app(self, org_id: str, event_type: str, message: str, payload: dict) -> None:
        if not self._redis:
            return
        import uuid
        notif = {
            "id": str(uuid.uuid4()),
            "event": event_type,
            "message": message,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "read": False,
        }
        key = f"notif:inbox:{org_id}"
        await self._redis.lpush(key, json.dumps(notif))
        await self._redis.ltrim(key, 0, 199)  # Keep last 200
        await self._redis.expire(key, NOTIF_TTL)

    async def _send_slack(self, webhook_url: str, event_type: str, message: str, payload: dict) -> None:
        emoji = {
            "test.failed": "🔴",
            "test.completed": "✅",
            "deploy.rolled_back": "⚠️",
            "deploy.failed": "❌",
            "security.issue_critical": "🛡️",
            "usage.warning_80pct": "📊",
            "usage.limit_reached": "🚫",
            "billing.payment_failed": "💳",
        }.get(event_type, "ℹ️")

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"{emoji} *{message}*"},
            }
        ]

        if payload.get("run_id"):
            blocks.append({
                "type": "actions",
                "elements": [{
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Details"},
                    "url": f"{APP_URL}/dashboard/test-runs",
                }],
            })

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(webhook_url, json={
                    "text": message,
                    "blocks": blocks,
                })
        except Exception as e:
            logger.warning(f"Slack notification failed: {e}")

    async def _send_email(self, to: str, event_type: str, message: str, payload: dict) -> None:
        """Send email via SMTP."""
        if not SMTP_HOST or not SMTP_USER:
            logger.debug(f"Email skipped (SMTP not configured): {message}")
            return

        subject_map = {
            "test.failed": "⚠️ Tests Failed — JarviisAI",
            "deploy.rolled_back": "🔄 Deployment Rolled Back — JarviisAI",
            "usage.warning_80pct": "📊 80% of your plan limit used — JarviisAI",
            "usage.limit_reached": "🚫 Plan limit reached — JarviisAI",
            "billing.trial_expired": "Your JarviisAI trial has ended",
            "billing.payment_failed": "⚠️ Payment failed — Action required",
            "billing.plan_changed": "Plan updated — JarviisAI",
            "security.issue_critical": "🛡️ Critical Security Issue Found — JarviisAI",
        }
        subject = subject_map.get(event_type, f"JarviisAI: {event_type}")

        # Build HTML email
        cta_url = f"{APP_URL}/dashboard"
        cta_text = "View Dashboard"
        if "billing" in event_type:
            cta_url = f"{APP_URL}/settings/billing"
            cta_text = "Manage Billing"
        elif "usage" in event_type:
            cta_url = f"{APP_URL}/settings/billing"
            cta_text = "Upgrade Plan"

        html = f"""
<!DOCTYPE html><html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px">
<div style="background:#0a0a1a;padding:24px;border-radius:12px;border:1px solid #2a2a4e">
  <img src="{APP_URL}/logo.png" alt="JarviisAI" style="height:32px;margin-bottom:20px"/>
  <h2 style="color:#f0f2ff;margin:0 0 12px">{subject}</h2>
  <p style="color:#a0a8c0;line-height:1.6">{message}</p>
  <a href="{cta_url}" style="display:inline-block;margin-top:20px;padding:12px 24px;background:#6d28d9;color:white;text-decoration:none;border-radius:8px;font-weight:600">{cta_text}</a>
</div>
<p style="color:#666;font-size:12px;margin-top:16px">
JarviisAI · 
<a href="{APP_URL}/settings/notifications">Manage notifications</a> · 
<a href="{APP_URL}/settings/notifications?unsubscribe=all">Unsubscribe</a>
</p>
</body></html>
"""
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            import ssl

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = EMAIL_FROM
            msg["To"] = to
            msg.attach(MIMEText(message, "plain"))
            msg.attach(MIMEText(html, "html"))

            context = ssl.create_default_context()
            with smtplib.SMTP(SMTP_HOST, int(os.getenv("SMTP_PORT", "587"))) as server:
                server.starttls(context=context)
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(EMAIL_FROM, to, msg.as_string())
        except Exception as e:
            logger.warning(f"Email notification failed to {to}: {e}")

    async def _send_teams(self, webhook_url: str, message: str, payload: dict) -> None:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(webhook_url, json={
                    "@type": "MessageCard",
                    "@context": "http://schema.org/extensions",
                    "summary": message,
                    "sections": [{"text": message}],
                })
        except Exception as e:
            logger.warning(f"Teams notification failed: {e}")

    async def _send_webhook(self, url: str, event_type: str, payload: dict) -> None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json={
                    "event": event_type,
                    "payload": payload,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "jarviis",
                })
        except Exception as e:
            logger.warning(f"Custom webhook failed ({url}): {e}")

    # ── Helpers ───────────────────────────────────────────────

    def _format_message(self, event_type: str, payload: dict) -> str:
        templates = {
            "test.failed": lambda p: f"Tests failed: {p.get('failed', 0)} failures in {p.get('total', 0)} tests ({p.get('pass_rate', 0)}% pass rate)",
            "test.completed": lambda p: f"Tests passed: {p.get('passed', 0)}/{p.get('total', 0)} tests ({p.get('pass_rate', 0)}% pass rate)",
            "deploy.rolled_back": lambda p: f"Deployment rolled back to previous version",
            "deploy.failed": lambda p: f"Deployment failed: {p.get('error', 'Unknown error')}",
            "security.issue_critical": lambda p: f"Critical security issue: {p.get('title', 'Security finding')}",
            "usage.warning_80pct": lambda p: f"You've used {p.get('pct', 80)}% of your monthly {p.get('metric', 'quota')} ({p.get('current', 0)}/{p.get('limit', 0)})",
            "usage.limit_reached": lambda p: f"Monthly limit reached: {p.get('current', 0)}/{p.get('limit', 0)} {p.get('metric', 'quota')} used. Upgrade to continue.",
            "billing.trial_expired": lambda p: "Your 2-day trial has ended. Upgrade to keep running tests.",
            "billing.payment_failed": lambda p: "Payment failed. Update your payment method to avoid service interruption.",
            "billing.plan_changed": lambda p: f"Plan updated to {p.get('plan', 'your new plan')}",
            "healing.applied": lambda p: f"Auto-healing fixed {p.get('healed', 0)} test selector(s)",
        }
        fn = templates.get(event_type, lambda p: f"Event: {event_type}")
        return fn(payload)

    async def _get_org_config(self, org_id: str) -> dict:
        if not self._redis:
            return {}
        try:
            data = await self._redis.get(f"notif:config:{org_id}")
            return json.loads(data) if data else {}
        except Exception:
            return {}


notification_service = NotificationService()
