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
from datetime import datetime, timedelta, timezone
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

# 외부 서비스 요청 수 (성공/실패 구분) — 에러율·성공률 계산용
external_request_total = Counter(
    "photo_api_external_request_total",
    "Total external API requests by service and outcome",
    ["service", "status"],  # status: success | failure
    registry=REGISTRY,
)

# --- Circuit Breaker ---
circuit_breaker_requests_total = Counter(
    "photo_api_circuit_breaker_requests_total",
    "Total number of requests passed through circuit breaker",
    ["service", "status"],  # status: success | failure | rejected
    registry=REGISTRY,
)

circuit_breaker_failures_total = Counter(
    "photo_api_circuit_breaker_failures_total",
    "Total number of failures by exception type",
    ["service", "exception_type"],
    registry=REGISTRY,
)

circuit_breaker_state_transitions_total = Counter(
    "photo_api_circuit_breaker_state_transitions_total",
    "Total number of state transitions",
    ["service", "from_state", "to_state"],
    registry=REGISTRY,
)

circuit_breaker_call_duration_seconds = Histogram(
    "photo_api_circuit_breaker_call_duration_seconds",
    "Circuit breaker function call duration in seconds",
    ["service"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
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
    ["service", "result"],  # result: success | failure
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

# 진행 중인 요청 수 (Graceful shutdown용)
in_flight_requests = Gauge(
    "photo_api_in_flight_requests",
    "Number of requests currently being processed",
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

# OBS Presigned URL(임시 URL) 요청량 — 이미지 업로드용
presigned_url_generation_total = Counter(
    "photo_api_presigned_url_generation_total",
    "Total number of OBS presigned (temp) URL generation attempts",
    ["result"],  # result: success | failure
    registry=REGISTRY,
)
# CDN Auth Token API 요청량
cdn_auth_token_requests_total = Counter(
    "photo_api_cdn_auth_token_requests_total",
    "Total CDN Auth Token API requests (image delivery URL generation)",
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
# 용량별 앨범 접근 시간 (사진 수 구간: empty/small/medium/large)
album_access_duration_seconds = Histogram(
    "photo_api_album_access_duration_seconds",
    "Album access request duration in seconds (get album with photos), by size bucket",
    ["size_bucket", "access_type"],  # size_bucket: empty|small|medium|large, access_type: authenticated|shared
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0),
    registry=REGISTRY,
)


def album_access_size_bucket(photo_count: int) -> str:
    """Return size_bucket label for album_access_duration_seconds (0=empty, 1-10=small, 11-50=medium, 51+=large)."""
    if photo_count == 0:
        return "empty"
    if photo_count <= 10:
        return "small"
    if photo_count <= 50:
        return "medium"
    return "large"


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
# 공유 링크 접속량(앨범별) — 접속량 많은 앨범 TOP 10 시각화용
share_link_access_by_album_total = Counter(
    "photo_api_share_link_access_by_album_total",
    "Total successful share link access count by album",
    ["album_id"],
    registry=REGISTRY,
)

# --- Business Growth Metrics ---
# 서비스 성장 지표: 회원수, 앨범 수, 사진 수 등
users_total = Gauge(
    "photo_api_users_total",
    "Total number of registered users",
    ["status"],  # status: total | active
    registry=REGISTRY,
)

albums_total = Gauge(
    "photo_api_albums_total",
    "Total number of albums",
    ["type"],  # type: total | shared (has share links)
    registry=REGISTRY,
)

photos_total = Gauge(
    "photo_api_photos_total",
    "Total number of photos",
    registry=REGISTRY,
)

share_links_total = Gauge(
    "photo_api_share_links_total",
    "Total number of share links",
    ["status"],  # status: total | active
    registry=REGISTRY,
)

# --- Object Storage Usage Metrics ---
# Object Storage 사용량 추적: 누가, 언제부터 용량이 급증했는지
object_storage_usage_bytes = Gauge(
    "photo_api_object_storage_usage_bytes",
    "Total object storage usage in bytes",
    registry=REGISTRY,
)

object_storage_usage_by_user_bytes = Gauge(
    "photo_api_object_storage_usage_by_user_bytes",
    "Object storage usage by user in bytes",
    ["user_id"],  # user_id: 사용자 ID
    registry=REGISTRY,
)

# 사진 업로드 시 실시간 업데이트용 Counter (시간별 추이 분석용)
photo_upload_size_total = Counter(
    "photo_api_photo_upload_size_total_bytes",
    "Total photo upload size in bytes (cumulative)",
    ["user_id"],  # user_id: 사용자 ID
    registry=REGISTRY,
)

# --- 비즈니스 관점 도메인 메트릭 (집계·KPI) ---
# 주기 집계(update_business_metrics)로 갱신되는 지표

# 사용자: 신규 가입 (기간별)
business_new_users_24h = Gauge(
    "photo_api_business_new_users_24h",
    "Number of new user registrations in the last 24 hours",
    registry=REGISTRY,
)
business_new_users_7d = Gauge(
    "photo_api_business_new_users_7d",
    "Number of new user registrations in the last 7 days",
    registry=REGISTRY,
)

# 앨범·사진: 사용자당/앨범당 평균 (engagement)
business_avg_albums_per_user = Gauge(
    "photo_api_business_avg_albums_per_user",
    "Average number of albums per user (total_albums / total_users)",
    registry=REGISTRY,
)
business_avg_photos_per_album = Gauge(
    "photo_api_business_avg_photos_per_album",
    "Average number of photos per album (total_photos / total_albums)",
    registry=REGISTRY,
)
business_avg_photos_per_user = Gauge(
    "photo_api_business_avg_photos_per_user",
    "Average number of photos per user (total_photos / total_users)",
    registry=REGISTRY,
)

# 앨범: 공유율 (%)
business_share_rate_percent = Gauge(
    "photo_api_business_share_rate_percent",
    "Percentage of albums that have at least one active share link",
    registry=REGISTRY,
)

# 사진: 최근 업로드 활동
business_photos_uploaded_24h = Gauge(
    "photo_api_business_photos_uploaded_24h",
    "Number of photos uploaded in the last 24 hours",
    registry=REGISTRY,
)

# 공유: 최근 생성·총 조회수
business_share_links_created_24h = Gauge(
    "photo_api_business_share_links_created_24h",
    "Number of share links created in the last 24 hours",
    registry=REGISTRY,
)
business_total_share_views = Gauge(
    "photo_api_business_total_share_views",
    "Total view count across all share links (sum of view_count)",
    registry=REGISTRY,
)

# Temp URL 업로드 추적: TTL 만료 후 confirm 없는 건 수 (주기 집계로 갱신)
temp_upload_incomplete_after_ttl = Gauge(
    "photo_api_temp_upload_incomplete_after_ttl",
    "Number of temp URL issuances not confirmed after URL expiry (expires_at < now, completed_at is null)",
    registry=REGISTRY,
)

# 인증: 가입·로그인 시도 (이벤트 기반 Counter)
user_registration_total = Counter(
    "photo_api_user_registration_total",
    "Total user registration attempts",
    ["result"],  # result: success | failure
    registry=REGISTRY,
)
user_login_total = Counter(
    "photo_api_user_login_total",
    "Total login attempts",
    ["result"],  # result: success | failure
    registry=REGISTRY,
)
jwt_token_validation_total = Counter(
    "photo_api_jwt_token_validation_total",
    "Total JWT token validation attempts (Bearer token on protected routes)",
    ["result"],  # result: success | failure
    registry=REGISTRY,
)

# 앨범별 Top 10 시각화용 (update_business_metrics에서 갱신, AlbumTop10Collector에서 노출)
_top10_album_photo_count: list[tuple[str, int]] = []  # (album_id, count)
_top10_album_storage_bytes: list[tuple[str, int]] = []  # (album_id, bytes)
_top10_album_share_views: list[tuple[str, int]] = []  # (album_id, views)


class AlbumTop10Collector:
    """Exposes Top 10 albums by photo count, storage size, and share views (low cardinality)."""

    def collect(self):
        m_photos = GaugeMetricFamily(
            "photo_api_album_top10_by_photo_count",
            "Top 10 albums by photo count (rank 1=highest)",
            labels=["rank", "album_id"],
        )
        for rank, (album_id, value) in enumerate(_top10_album_photo_count[:10], start=1):
            m_photos.add_metric([str(rank), str(album_id)], float(value))
        if _top10_album_photo_count:
            yield m_photos

        m_storage = GaugeMetricFamily(
            "photo_api_album_top10_by_storage_bytes",
            "Top 10 albums by total image storage in bytes (rank 1=highest)",
            labels=["rank", "album_id"],
        )
        for rank, (album_id, value) in enumerate(_top10_album_storage_bytes[:10], start=1):
            m_storage.add_metric([str(rank), str(album_id)], float(value))
        if _top10_album_storage_bytes:
            yield m_storage

        m_views = GaugeMetricFamily(
            "photo_api_album_top10_by_share_views",
            "Top 10 albums by share link view count (rank 1=highest)",
            labels=["rank", "album_id"],
        )
        for rank, (album_id, value) in enumerate(_top10_album_share_views[:10], start=1):
            m_views.add_metric([str(rank), str(album_id)], float(value))
        if _top10_album_share_views:
            yield m_views


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


async def update_business_metrics() -> None:
    """
    DB에서 비즈니스 메트릭을 집계하여 업데이트.
    
    주기적으로 호출되어 서비스 성장 지표를 업데이트합니다:
    - 회원수 (전체, 활성)
    - 앨범 수 (전체, 공유 앨범)
    - 사진 수
    - 공유 링크 수 (전체, 활성)
    - Object Storage 사용량 (전체, 사용자별)
    """
    try:
        from app.database import get_db_context
        from app.models.user import User
        from app.models.album import Album, AlbumPhoto
        from app.models.photo import Photo
        from app.models.share import ShareLink
        from sqlalchemy import select, func

        now = datetime.now(timezone.utc)
        cutoff_24h = now - timedelta(hours=24)
        cutoff_7d = now - timedelta(days=7)

        async with get_db_context() as db:
            # 회원수 집계
            total_users_result = await db.execute(select(func.count(User.id)))
            total_users = total_users_result.scalar() or 0

            active_users_result = await db.execute(
                select(func.count(User.id)).where(User.is_active == True)
            )
            active_users = active_users_result.scalar() or 0

            # 신규 가입 (24h, 7d)
            new_users_24h_result = await db.execute(
                select(func.count(User.id)).where(User.created_at >= cutoff_24h)
            )
            new_users_24h = new_users_24h_result.scalar() or 0
            new_users_7d_result = await db.execute(
                select(func.count(User.id)).where(User.created_at >= cutoff_7d)
            )
            new_users_7d = new_users_7d_result.scalar() or 0

            # 앨범 수 집계
            total_albums_result = await db.execute(select(func.count(Album.id)))
            total_albums = total_albums_result.scalar() or 0

            # 공유 앨범 수 (share_links가 있는 앨범)
            shared_albums_result = await db.execute(
                select(func.count(func.distinct(Album.id)))
                .join(ShareLink, ShareLink.album_id == Album.id)
                .where(ShareLink.is_active == True)
            )
            shared_albums = shared_albums_result.scalar() or 0

            # 사진 수 집계
            total_photos_result = await db.execute(select(func.count(Photo.id)))
            total_photos = total_photos_result.scalar() or 0

            # 최근 24h 업로드 사진 수
            photos_24h_result = await db.execute(
                select(func.count(Photo.id)).where(Photo.created_at >= cutoff_24h)
            )
            photos_uploaded_24h = photos_24h_result.scalar() or 0

            # 공유 링크 수 집계
            total_share_links_result = await db.execute(select(func.count(ShareLink.id)))
            total_share_links = total_share_links_result.scalar() or 0

            active_share_links_result = await db.execute(
                select(func.count(ShareLink.id))
                .where(ShareLink.is_active == True)
                .where(
                    (ShareLink.expires_at.is_(None)) |
                    (ShareLink.expires_at > func.now())
                )
            )
            active_share_links = active_share_links_result.scalar() or 0

            # 최근 24h 공유 링크 생성 수
            share_links_24h_result = await db.execute(
                select(func.count(ShareLink.id)).where(ShareLink.created_at >= cutoff_24h)
            )
            share_links_created_24h = share_links_24h_result.scalar() or 0

            # 공유 링크 총 조회수
            total_share_views_result = await db.execute(select(func.sum(ShareLink.view_count)))
            total_share_views = total_share_views_result.scalar() or 0

            # Object Storage 사용량 집계 (사진 파일 크기 합계)
            total_storage_result = await db.execute(
                select(func.sum(Photo.file_size))
            )
            total_storage = total_storage_result.scalar() or 0

            # 사용자별 Object Storage 사용량
            user_storage_result = await db.execute(
                select(Photo.owner_id, func.sum(Photo.file_size).label("total_size"))
                .group_by(Photo.owner_id)
            )
            user_storage_map = {row.owner_id: row.total_size for row in user_storage_result}

            # 메트릭 업데이트 (기존)
            users_total.labels(status="total").set(total_users)
            users_total.labels(status="active").set(active_users)

            albums_total.labels(type="total").set(total_albums)
            albums_total.labels(type="shared").set(shared_albums)

            photos_total.set(total_photos)

            share_links_total.labels(status="total").set(total_share_links)
            share_links_total.labels(status="active").set(active_share_links)

            object_storage_usage_bytes.set(total_storage)

            # 비즈니스 도메인 메트릭
            business_new_users_24h.set(new_users_24h)
            business_new_users_7d.set(new_users_7d)

            if total_users > 0:
                business_avg_albums_per_user.set(round(total_albums / total_users, 2))
                business_avg_photos_per_user.set(round(total_photos / total_users, 2))
            else:
                business_avg_albums_per_user.set(0)
                business_avg_photos_per_user.set(0)

            if total_albums > 0:
                business_avg_photos_per_album.set(round(total_photos / total_albums, 2))
            else:
                business_avg_photos_per_album.set(0)

            if total_albums > 0:
                business_share_rate_percent.set(
                    round(shared_albums / total_albums * 100, 2)
                )
            else:
                business_share_rate_percent.set(0)

            business_photos_uploaded_24h.set(photos_uploaded_24h)
            business_share_links_created_24h.set(share_links_created_24h)
            business_total_share_views.set(total_share_views)

            # 사용자별 사용량 업데이트
            for user_id, size in user_storage_map.items():
                object_storage_usage_by_user_bytes.labels(user_id=str(user_id)).set(size)

            # 앨범별 Top 10 (이미지 개수, 저장 용량, 공유 조회수)
            global _top10_album_photo_count, _top10_album_storage_bytes, _top10_album_share_views
            top_photos_result = await db.execute(
                select(AlbumPhoto.album_id, func.count(AlbumPhoto.photo_id).label("cnt"))
                .group_by(AlbumPhoto.album_id)
                .order_by(func.count(AlbumPhoto.photo_id).desc())
                .limit(10)
            )
            _top10_album_photo_count = [(str(r.album_id), r.cnt) for r in top_photos_result.fetchall()]

            top_storage_result = await db.execute(
                select(AlbumPhoto.album_id, func.coalesce(func.sum(Photo.file_size), 0).label("total_bytes"))
                .join(Photo, Photo.id == AlbumPhoto.photo_id)
                .group_by(AlbumPhoto.album_id)
                .order_by(func.sum(Photo.file_size).desc())
                .limit(10)
            )
            _top10_album_storage_bytes = [(str(r.album_id), int(r.total_bytes)) for r in top_storage_result.fetchall()]

            top_views_result = await db.execute(
                select(ShareLink.album_id, func.coalesce(func.sum(ShareLink.view_count), 0).label("views"))
                .group_by(ShareLink.album_id)
                .order_by(func.sum(ShareLink.view_count).desc())
                .limit(10)
            )
            _top10_album_share_views = [(str(r.album_id), int(r.views)) for r in top_views_result.fetchall()]

            # Temp URL 업로드 추적: TTL 만료 후 미확인 건 수
            from app.services.temp_upload_tracking import aggregate_incomplete_after_ttl
            agg = await aggregate_incomplete_after_ttl(db, now=now, limit=50_000)
            temp_upload_incomplete_after_ttl.set(agg["total_count"])

    except Exception as e:
        logger.warning("Business metrics update failed: %s", e, exc_info=False)


async def business_metrics_loop() -> None:
    """
    백그라운드 루프: 주기적으로 비즈니스 메트릭을 업데이트.
    """
    interval = 60  # 60초마다 업데이트
    logger.info(
        "Business metrics collection enabled: interval=%ds",
        interval,
        extra={"event": "lifecycle"},
    )
    
    # 시작 시 즉시 한 번 실행
    await update_business_metrics()
    
    while True:
        await asyncio.sleep(interval)
        try:
            await update_business_metrics()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("Business metrics update failed: %s", e, exc_info=False)


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
    Context manager to record external request duration, total count, and errors.
    Use around NHN Storage/CDN/Log HTTP calls.
    """
    start = time.perf_counter()
    exc_raised = None
    try:
        yield
    except Exception as e:
        exc_raised = e
        external_request_errors_total.labels(service=service).inc()
        external_request_total.labels(service=service, status="failure").inc()
        raise
    finally:
        duration = time.perf_counter() - start
        result = "failure" if exc_raised is not None else "success"
        if exc_raised is None:
            external_request_total.labels(service=service, status="success").inc()
        external_request_duration_seconds.labels(service=service, result=result).observe(duration)


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
    if (settings.region or "").strip():
        grouping_key["region"] = (settings.region or "").strip()
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

    # Node/App identity (region = REGION env)
    app_info = Gauge(
        "photo_api_app_info",
        "Application and node identity (labels only, value is 1)",
        ["node", "app", "version", "environment", "region"],
        registry=REGISTRY,
    )
    app_info.labels(
        node=node,
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
        region=(settings.region or "").strip() or "unknown",
    ).set(1)

    # Log queue size (custom collector)
    REGISTRY.register(LogQueueSizeCollector())
    REGISTRY.register(AlbumTop10Collector())

    # FastAPI metrics — status 라벨을 2xx/3xx 대신 구체 코드(200, 201, 404, 500 등)로 노출
    Instrumentator(should_group_status_codes=False).instrument(app).expose(
        app, endpoint="/metrics"
    )
