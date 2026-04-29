"""JarviisAI — COBOL/Mainframe Testing Service"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import logging, os
from app.core.logging_config import configure_logging

from app.services.cobol_analyzer import analyzer
from app.services.cobol_generator import generator
from app.core.metrics import setup_metrics

logging.basicConfig(level=os.getenv("LOG_LEVEL","info").upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("jarviis.cobol")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🖥️  COBOL/Mainframe Testing Engine ready")
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

app = FastAPI(title="JarviisAI COBOL Testing Engine", version="1.0.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=INTERNAL_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class AnalyzeRequest(BaseModel):
    source: str
    filename: str = "program.cbl"
    generate_tests: bool = True


class AnalyzeResponse(BaseModel):
    program_id: str
    total_lines: int
    comment_lines: int
    paragraph_count: int
    cyclomatic_complexity: int
    called_programs: list
    copy_members: list
    dead_paragraphs: list
    warnings: list
    data_item_count: int
    paragraphs: list
    test_artifacts: Optional[dict] = None


setup_metrics(app, service_name="cobol")


@app.get("/health")
async def health():
    return {
        "service": "cobol-tester",
        "status": "ok",
        "ai_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
    }


@app.post("/api/v1/cobol/analyze", response_model=AnalyzeResponse)
async def analyze_cobol(data: AnalyzeRequest):
    """
    Analyze a COBOL source file and optionally generate test artifacts.
    """
    try:
        program = analyzer.analyze(data.source, data.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"COBOL parse error: {str(e)}")

    test_artifacts = None
    if data.generate_tests:
        try:
            # Pass first 50 lines as snippet for AI context
            snippet = "\n".join(data.source.splitlines()[:50])
            test_artifacts = await generator.generate(program, snippet)
        except Exception as e:
            logger.error(f"Test generation error: {e}", exc_info=True)
            test_artifacts = {"error": str(e)}

    return AnalyzeResponse(
        program_id=program.program_id,
        total_lines=program.total_lines,
        comment_lines=program.comment_lines,
        paragraph_count=len(program.paragraphs),
        cyclomatic_complexity=program.cyclomatic_complexity,
        called_programs=program.called_programs,
        copy_members=program.copy_members,
        dead_paragraphs=program.dead_paragraphs,
        warnings=program.warnings,
        data_item_count=len(program.data_items),
        paragraphs=[
            {
                "name": p.name,
                "lines": len(p.lines),
                "cyclomatic_complexity": p.cyclomatic_complexity,
                "perform_count": p.perform_count,
                "calls": p.calls,
                "gotos": p.gotos,
            }
            for p in program.paragraphs
        ],
        test_artifacts=test_artifacts,
    )


@app.post("/api/v1/cobol/upload")
async def upload_cobol(file: UploadFile = File(...)):
    """Upload a COBOL source file for analysis."""
    # File type validation
    ALLOWED_EXTENSIONS = {".cbl", ".cob", ".cpy", ".pco", ".txt", ".jcl"}
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Accepted: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Content-type validation
    content_type = file.content_type or ""
    if content_type and content_type not in (
        "text/plain", "text/x-cobol", "application/octet-stream",
        "text/x-jcl", "", "application/x-cobol"
    ):
        raise HTTPException(status_code=400, detail=f"Content type '{content_type}' not allowed")

    # Size limit: 10MB
    MAX_SIZE_BYTES = 10 * 1024 * 1024
    file_bytes = await file.read(MAX_SIZE_BYTES + 1)
    if len(file_bytes) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is 10MB."
        )

    try:
        source = file_bytes.decode("utf-8", errors="replace")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decode file as text")
    program = analyzer.analyze(source, file.filename or "upload.cbl")
    return {
        "program_id": program.program_id,
        "total_lines": program.total_lines,
        "paragraph_count": len(program.paragraphs),
        "complexity": program.cyclomatic_complexity,
        "warnings": program.warnings,
    }
