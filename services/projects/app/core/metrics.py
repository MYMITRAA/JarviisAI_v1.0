"""
Prometheus metrics middleware for JarviisAI services.
Exposes /metrics endpoint for Prometheus scraping.

Tracks:
  - http_requests_total (counter)
  - http_request_duration_seconds (histogram)
  - http_requests_in_progress (gauge)

Usage in any FastAPI app:
  from app.core.metrics import setup_metrics
  setup_metrics(app, service_name="projects")
"""

import time
from fastapi import FastAPI, Request, Response
from fastapi.routing import APIRoute

# Optional prometheus_client — graceful degradation if not installed
try:
    from prometheus_client import (
        Counter, Histogram, Gauge, generate_latest,
        CONTENT_TYPE_LATEST, CollectorRegistry, REGISTRY
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


def setup_metrics(app: FastAPI, service_name: str = "jarviis") -> None:
    """
    Add /metrics endpoint and request tracking middleware to a FastAPI app.
    Safe to call even if prometheus_client is not installed.
    """
    if not PROMETHEUS_AVAILABLE:
        @app.get("/metrics", include_in_schema=False)
        async def metrics_unavailable():
            return Response(
                content="# prometheus_client not installed\n",
                media_type="text/plain",
            )
        return

    # ── Metric definitions ────────────────────────────────────
    REQUEST_COUNT = Counter(
        f"jarviis_{service_name}_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status_code"],
        registry=REGISTRY,
    )
    REQUEST_LATENCY = Histogram(
        f"jarviis_{service_name}_http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "path"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        registry=REGISTRY,
    )
    REQUESTS_IN_PROGRESS = Gauge(
        f"jarviis_{service_name}_http_requests_in_progress",
        "HTTP requests currently being processed",
        ["method", "path"],
        registry=REGISTRY,
    )

    # ── Metrics endpoint ──────────────────────────────────────
    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(
            content=generate_latest(REGISTRY),
            media_type=CONTENT_TYPE_LATEST,
        )

    # ── Middleware ────────────────────────────────────────────
    @app.middleware("http")
    async def track_requests(request: Request, call_next):
        # Normalize path — replace UUIDs and IDs with placeholders
        path = _normalize_path(request.url.path)
        method = request.method

        REQUESTS_IN_PROGRESS.labels(method=method, path=path).inc()
        start = time.time()

        try:
            response = await call_next(request)
            duration = time.time() - start
            status = str(response.status_code)

            REQUEST_COUNT.labels(method=method, path=path, status_code=status).inc()
            REQUEST_LATENCY.labels(method=method, path=path).observe(duration)

            return response
        except Exception as e:
            duration = time.time() - start
            REQUEST_COUNT.labels(method=method, path=path, status_code="500").inc()
            REQUEST_LATENCY.labels(method=method, path=path).observe(duration)
            raise
        finally:
            REQUESTS_IN_PROGRESS.labels(method=method, path=path).dec()


def _normalize_path(path: str) -> str:
    """Replace dynamic path segments with placeholders to avoid high cardinality."""
    import re
    # UUID pattern
    path = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{id}",
        path,
    )
    # Numeric IDs
    path = re.sub(r"/\d+(?=/|$)", "/{id}", path)
    return path
