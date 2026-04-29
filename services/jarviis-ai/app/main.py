import os
"""JarviisAI — AGI Assistant Service"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import logging, os
from app.core.logging_config import configure_logging

from app.services.assistant import assistant
from app.core.metrics import setup_metrics

logging.basicConfig(level=os.getenv("LOG_LEVEL","info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.assistant")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🤖 Jarviis AI Assistant ready")
    yield



APP_URL = os.getenv("APP_URL", "http://localhost:3000")
INTERNAL_ORIGINS = [APP_URL, "http://localhost:3000", "http://jarviis-frontend:3000", "http://api-gateway:8000"]


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

app = FastAPI(title="JarviisAI AGI Assistant", version="1.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_methods=["*"], allow_headers=["*"])


class ChatRequest(BaseModel):
    message: str
    org_id: str
    conversation_history: Optional[List[dict]] = []
    access_token: Optional[str] = ""


setup_metrics(app, service_name="jarviis_ai")


@app.get("/health")
async def health():
    return {
        "service": "jarviis-ai",
        "status": "ok",
        "ai_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
    }


@app.post("/api/v1/chat")
async def chat(data: ChatRequest):
    try:
        result = await assistant.chat(
            message=data.message,
            org_id=data.org_id,
            conversation_history=data.conversation_history or [],
            access_token=data.access_token or "",
        )
        return result
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
