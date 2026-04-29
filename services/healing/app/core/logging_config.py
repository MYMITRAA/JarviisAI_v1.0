"""
Structured JSON logging for JarviisAI services.
Replaces plain text basicConfig with JSON-formatted log records.

Every log line becomes:
{"timestamp": "2026-04-28T10:00:00Z", "level": "INFO", "service": "projects",
 "org_id": "...", "run_id": "...", "msg": "Test run created", "trace_id": "..."}
"""

import json
import logging
import sys
import os
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def __init__(self, service_name: str = ""):
        super().__init__()
        self.service_name = service_name or os.getenv("SERVICE_NAME", "jarviis")

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level":     record.levelname,
            "service":   self.service_name,
            "logger":    record.name,
            "msg":       record.getMessage(),
        }

        # Include exception info
        if record.exc_info:
            log_obj["exc_info"] = self.formatException(record.exc_info)

        # Include any extra fields attached to the record
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            ):
                try:
                    json.dumps(value)  # ensure serialisable
                    log_obj[key] = value
                except (TypeError, ValueError):
                    log_obj[key] = str(value)

        return json.dumps(log_obj, default=str)


def configure_logging(service_name: str = "", level: str = "INFO") -> None:
    """
    Replace the root logger's handler with a JSON formatter.
    Call this once at service startup.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service_name=service_name))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Suppress noisy third-party loggers
    for noisy in ("uvicorn.access", "httpcore", "httpx", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
