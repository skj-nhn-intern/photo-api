"""
Prometheus metrics for stability, high availability, and performance.

- FastAPI: request count, latency (Instrumentator)
- Node/instance: app_info
- Stability: exceptions_total, db_errors_total, external_request_errors_total, log_queue_size
- HA: ready gauge (1=up, 0=shutting down)
- Performance: external_request_duration_seconds, login_duration_seconds, active_sessions
- Pushgateway: 선택 시 주기적으로 메트릭 푸시 (PROMETHEUS_PUSHGATEWAY_URL)
"""
import asyncio
import logging
import socket
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from urllib.parse import quote

import httpx
from prometheus_client import REGISTRY, Counter, Gauge, Histogram, pushadd_to_gateway
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

# 로그인 지연(응답 시간) — 1,000ms/3,000ms 초과율 모니터링용 버킷
login_duration_seconds = Histogram(
    "photo_api_login_duration_seconds",
    "Login request duration in seconds",
    ["result"],  # success | failure
    buckets=(0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 3.0, 5.0),
    registry=REGISTRY,
)

# 활성화된 세션 수 (인증된 요청이 처리 중인 수, JWT 기준)
active_sessions = Gauge(
    "photo_api_active_sessions",
    "Number of in-flight requests with valid authentication",
    registry=REGISTRY,
)

# --- Rate Limiting ---
rate_limit_hits_total = Counter(
    "photo_api_rate_limit_hits_total",
    "Total number of rate limit hits (requests blocked)",
    ["endpoint", "client_id"],  # client_id는 IP 주소 일부 (개인정보 보호)
    registry=REGISTRY,
)

rate_limit_requests_total = Counter(
    "photo_api_rate_limit_requests_total",
    "Total number of requests checked for rate limiting",
    ["endpoint", "status"],  # status: allowed | blocked
    registry=REGISTRY,
)

# --- Share Link Access Patterns ---
share_link_access_total = Counter(
    "photo_api_share_link_access_total",
    "Total number of share link access attempts",
    ["token_status", "result"],  # token_status: valid | invalid | expired, result: success | denied
    registry=REGISTRY,
)

share_link_brute_force_attempts = Counter(
    "photo_api_share_link_brute_force_attempts_total",
    "Total number of brute force attempts on share links (invalid token attempts)",
    ["client_id"],  # client_id는 IP 주소 일부
    registry=REGISTRY,
)

share_link_access_duration_seconds = Histogram(
    "photo_api_share_link_access_duration_seconds",
    "Share link access request duration in seconds",
    ["token_status", "result"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=REGISTRY,
)

share_link_image_access_total = Counter(
    "photo_api_share_link_image_access_total",
    "Total number of share link image access attempts",
    ["token_status", "photo_in_album"],  # photo_in_album: yes | no
    registry=REGISTRY,
)

# --- Image Access Patterns ---
image_access_total = Counter(
    "photo_api_image_access_total",
    "Total number of image access attempts",
    ["access_type", "result"],  # access_type: authenticated | shared, result: success | denied
    registry=REGISTRY,
)

image_access_duration_seconds = Histogram(
    "photo_api_image_access_duration_seconds",
    "Image access request duration in seconds",
    ["access_type", "result"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=REGISTRY,
)

# --- Photo Upload Metrics ---
photo_upload_total = Counter(
    "photo_api_photo_upload_total",
    "Total number of photo upload attempts",
    ["upload_method", "result"],  # upload_method: presigned | direct, result: success | failure
    registry=REGISTRY,
)

photo_upload_file_size_bytes = Histogram(
    "photo_api_photo_upload_file_size_bytes",
    "Photo upload file size in bytes",
    ["upload_method"],
    buckets=(1024, 10240, 102400, 512000, 1024000, 2048000, 5120000, 10240000),  # 1KB to 10MB
    registry=REGISTRY,
)

presigned_url_generation_total = Counter(
    "photo_api_presigned_url_generation_total",
    "Total number of presigned URL generation attempts",
    ["result"],  # result: success | failure
    registry=REGISTRY,
)

photo_upload_confirm_total = Counter(
    "photo_api_photo_upload_confirm_total",
    "Total number of photo upload confirmation attempts",
    ["result"],  # result: success | failure
    registry=REGISTRY,
)

# --- Album Metrics ---
album_operations_total = Counter(
    "photo_api_album_operations_total",
    "Total number of album operations",
    ["operation", "result"],  # operation: create | update | delete, result: success | failure
    registry=REGISTRY,
)

album_photo_operations_total = Counter(
    "photo_api_album_photo_operations_total",
    "Total number of album photo operations",
    ["operation", "result"],  # operation: add | remove, result: success | failure
    registry=REGISTRY,
)

# --- Share Link Creation Metrics ---
share_link_creation_total = Counter(
    "photo_api_share_link_creation_total",
    "Total number of share link creation attempts",
    ["result"],  # result: success | failure
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
        # pushadd_to_gateway uses POST; push_to_gateway uses PUT (some gateways/proxies return 501 for PUT)
        pushadd_to_gateway(url, job=job, registry=REGISTRY, grouping_key=grouping_key)
    except Exception as e:
        logger.warning("Pushgateway push failed: %s", e, exc_info=False)


async def push_node_exporter_to_gateway() -> None:
    """
    node_exporter(127.0.0.1:9100) 메트릭을 읽어 Pushgateway로 전송.
    Pushgateway만 스크래핑해도 앱 + 호스트 메트릭을 함께 볼 수 있음.
    """
    settings = get_settings()
    base = (settings.prometheus_pushgateway_url or "").strip().rstrip("/")
    if not base:
        return
    instance = (settings.instance_ip or _node_identity()).strip() or "unknown"
    path = f"/metrics/job/node_exporter/instance/{quote(instance, safe='')}"
    url = f"{base}{path}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get("http://127.0.0.1:9100/metrics")
            r.raise_for_status()
            body = r.text
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(url, content=body, headers={"Content-Type": "text/plain; charset=utf-8"})
    except httpx.ConnectError:
        logger.debug("node_exporter push skip: 127.0.0.1:9100 unreachable (not running?)")
    except Exception as e:
        logger.debug("node_exporter push failed: %s", e)


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
            await push_node_exporter_to_gateway()
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
