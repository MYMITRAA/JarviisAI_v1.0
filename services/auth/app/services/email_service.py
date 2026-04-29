"""Email service — async SMTP via aiosmtplib."""

import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.core.config import settings
import logging

logger = logging.getLogger("jarviis.auth.email")


class EmailService:

    async def _send(self, to: str, subject: str, html: str, text: str = None) -> bool:
        """Send an email. Returns True on success, logs and returns False on failure."""
        if not settings.SMTP_USER:
            logger.warning(f"SMTP not configured — email not sent to {to}: {subject}")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"JarviisAI <{settings.EMAIL_FROM}>"
        msg["To"] = to

        if text:
            msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                start_tls=True,
            )
            logger.info(f"Email sent to {to}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            return False

    async def send_verification_email(self, to: str, token: str, full_name: str = None) -> bool:
        verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        name = full_name or "Developer"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0D0D1A; color: #fff; padding: 40px; border-radius: 12px;">
          <h1 style="color: #6C63FF; font-size: 28px; margin-bottom: 8px;">JarviisAI</h1>
          <p style="color: #00D4FF; font-size: 14px; margin-top: 0;">Test. Deploy. Heal. Autonomously.</p>
          <hr style="border-color: #6C63FF; margin: 24px 0;">
          <h2 style="color: #fff;">Verify your email, {name} 👋</h2>
          <p style="color: #C8C8E0;">You're one click away from autonomous testing. Verify your email to initialize your instance.</p>
          <a href="{verify_url}"
             style="display: inline-block; background: #6C63FF; color: #fff; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: bold; margin: 24px 0;">
            Verify Email Address
          </a>
          <p style="color: #666; font-size: 12px;">This link expires in 24 hours. If you didn't create an account, ignore this email.</p>
        </div>
        """
        return await self._send(to, "Verify your JarviisAI account", html)

    async def send_password_reset_email(self, to: str, token: str) -> bool:
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0D0D1A; color: #fff; padding: 40px; border-radius: 12px;">
          <h1 style="color: #6C63FF; font-size: 28px;">JarviisAI</h1>
          <hr style="border-color: #6C63FF; margin: 24px 0;">
          <h2 style="color: #fff;">Reset your credentials</h2>
          <p style="color: #C8C8E0;">We received a request to reset your password. Click below to create a new one.</p>
          <a href="{reset_url}"
             style="display: inline-block; background: #FF2D55; color: #fff; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: bold; margin: 24px 0;">
            Reset Credentials
          </a>
          <p style="color: #666; font-size: 12px;">This link expires in 1 hour. If you didn't request this, ignore this email.</p>
        </div>
        """
        return await self._send(to, "Reset your JarviisAI credentials", html)

    async def send_invite_email(self, to: str, inviter_name: str, org_name: str, token: str, role: str) -> bool:
        invite_url = f"{settings.FRONTEND_URL}/invite/accept?token={token}"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0D0D1A; color: #fff; padding: 40px; border-radius: 12px;">
          <h1 style="color: #6C63FF; font-size: 28px;">JarviisAI</h1>
          <hr style="border-color: #6C63FF; margin: 24px 0;">
          <h2 style="color: #fff;">You've been invited to <span style="color: #00D4FF;">{org_name}</span></h2>
          <p style="color: #C8C8E0;"><strong>{inviter_name}</strong> has invited you to join as a <strong>{role}</strong>.</p>
          <a href="{invite_url}"
             style="display: inline-block; background: #00C9A7; color: #fff; padding: 14px 28px; border-radius: 8px; text-decoration: none; font-weight: bold; margin: 24px 0;">
            Accept Invite &amp; Initialize Instance
          </a>
          <p style="color: #666; font-size: 12px;">This invite expires in 7 days.</p>
        </div>
        """
        return await self._send(to, f"You're invited to {org_name} on JarviisAI", html)


email_service = EmailService()
