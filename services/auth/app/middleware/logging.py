"""Structured request logging with unique request IDs."""

import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("jarviis.auth.requests")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        # Attach request ID for use in handlers
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                f"[{request_id}] {request.method} {request.url.path} — EXCEPTION: {exc}",
                exc_info=True,
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} "
            f"{response.status_code} {duration_ms}ms "
            f"ip={request.client.host if request.client else 'unknown'}"
        )

        response.headers["X-Request-ID"] = request_id
        return response
