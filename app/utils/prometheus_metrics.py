"""
Prometheus metrics for stability, high availability, and performance.

- FastAPI: request count, latency (Instrumentator)
- Node/instance: app_info
- Stability: exceptions_total, db_errors_total, external_request_errors_total, log_queue_size
- HA: ready gauge (1=up, 0=shutting down)
- Performance: external_request_duration_seconds
"""
import socket
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from prometheus_client import REGISTRY, Counter, Gauge, Histogram
from prometheus_client.core import GaugeMetricFamily
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import get_settings

# --- Stability ---
exceptions_total = Counter(
    "photo_api_exceptions_total",
    "Total unhandled exceptions",
    registry=REGISTRY,
)
db_errors_total = Counter(
    "photo_api_db_errors_total",
    "Total database session/transaction errors",
    registry=REGISTRY,
)
external_request_errors_total = Counter(
    "photo_api_external_request_errors_total",
    "Total external API request failures",
    ["service"],
    registry=REGISTRY,
)

# --- HA ---
ready = Gauge(
    "photo_api_ready",
    "Application ready (1=up, 0=shutting down)",
    registry=REGISTRY,
)

# --- Performance ---
external_request_duration_seconds = Histogram(
    "photo_api_external_request_duration_seconds",
    "External API request duration in seconds",
    ["service"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)


class LogQueueSizeCollector:
    """Collector that reports NHN logger queue size (backpressure indicator)."""

    def collect(self):
        try:
            from app.services.nhn_logger import get_logger_service
            size = get_logger_service().queue_size()
        except Exception:
            size = 0
        metric = GaugeMetricFamily(
            "photo_api_log_queue_size",
            "NHN log queue length (high = backpressure)",
        )
        metric.add_metric([], float(size))
        yield metric


def _node_identity() -> str:
    """Node/instance identifier: NODE_NAME env or hostname."""
    settings = get_settings()
    if settings.node_name:
        return settings.node_name
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


@asynccontextmanager
async def record_external_request(service: str) -> AsyncGenerator[None, None]:
    """
    Context manager to record external request duration and errors.
    Use around NHN Storage/CDN/Log HTTP calls.
    """
    start = time.perf_counter()
    exc_raised = None
    try:
        yield
    except Exception as e:
        exc_raised = e
        external_request_errors_total.labels(service=service).inc()
        raise
    finally:
        duration = time.perf_counter() - start
        external_request_duration_seconds.labels(service=service).observe(duration)


def setup_prometheus(app) -> None:
    """
    Register Prometheus instrumentation and custom metrics.

    1. app_info + Instrumentator (FastAPI request metrics).
    2. Stability/HA/performance: exceptions, db_errors, external, ready, log_queue.
    """
    settings = get_settings()
    node = _node_identity()

    # Node/App identity
    app_info = Gauge(
        "photo_api_app_info",
        "Application and node identity (labels only, value is 1)",
        ["node", "app", "version", "environment"],
        registry=REGISTRY,
    )
    app_info.labels(
        node=node,
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
    ).set(1)

    # Log queue size (custom collector)
    REGISTRY.register(LogQueueSizeCollector())

    # FastAPI metrics
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
