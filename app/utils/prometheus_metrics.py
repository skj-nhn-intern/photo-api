"""
Prometheus metrics for stability, high availability, and performance.

- FastAPI: request count, latency (Instrumentator)
- Node/instance: app_info
- Stability: exceptions_total, db_errors_total, external_request_errors_total, log_queue_size
- HA: ready gauge (1=up, 0=shutting down)
- Performance: external_request_duration_seconds
- Pushgateway: 선택 시 주기적으로 메트릭 푸시 (PROMETHEUS_PUSHGATEWAY_URL)
"""
import asyncio
import logging
import socket
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from prometheus_client import REGISTRY, Counter, Gauge, Histogram, push_to_gateway
from prometheus_client.core import GaugeMetricFamily
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import get_settings

logger = logging.getLogger(__name__)

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


def push_metrics_to_gateway() -> None:
    """
    Push current registry to Prometheus Pushgateway.
    Called periodically when PROMETHEUS_PUSHGATEWAY_URL is set.
    """
    settings = get_settings()
    url = (settings.prometheus_pushgateway_url or "").strip()
    if not url:
        return
    job = "photo-api"
    grouping_key = {"instance": settings.instance_ip or _node_identity()}
    try:
        push_to_gateway(url, job=job, registry=REGISTRY, grouping_key=grouping_key)
    except Exception as e:
        logger.warning("Pushgateway push failed: %s", e, exc_info=False)


async def pushgateway_loop() -> None:
    """
    Background loop: push metrics to Pushgateway at configured interval.
    Stops when PROMETHEUS_PUSHGATEWAY_URL is not set.
    Push is run in thread pool to avoid blocking the event loop.
    """
    settings = get_settings()
    url = (settings.prometheus_pushgateway_url or "").strip()
    if not url:
        return
    interval = max(15, settings.prometheus_push_interval_seconds)
    logger.info(
        "Pushgateway enabled: url=%s interval=%ds",
        url,
        interval,
        extra={"event": "lifecycle"},
    )
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(interval)
        try:
            await loop.run_in_executor(None, push_metrics_to_gateway)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("Pushgateway push failed: %s", e, exc_info=False)


def setup_prometheus(app) -> None:
    """
    Register Prometheus instrumentation and custom metrics.

    1. app_info + Instrumentator (FastAPI request metrics).
    2. Stability/HA/performance: exceptions, db_errors, external, ready, log_queue.
    3. /metrics 엔드포인트 노출 (스크래핑용).
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
