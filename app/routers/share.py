"""
Share router for public album access.
"""
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.schemas.share import SharedAlbumResponse
from app.services.album import AlbumService
from app.services.photo import PhotoService
from app.middlewares.rate_limit_middleware import get_rate_limit_decorator, get_client_identifier
from app.utils.prometheus_metrics import (
    album_access_duration_seconds,
    album_access_size_bucket,
    image_access_total,
    image_access_duration_seconds,
    share_link_access_total,
    share_link_access_by_album_total,
    share_link_brute_force_attempts,
    share_link_access_duration_seconds,
    share_link_image_access_total,
    rate_limit_requests_total,
)
from fastapi import Request

logger = logging.getLogger("app.share")
router = APIRouter(prefix="/share", tags=["Shared Albums"])

# Rate limiting 설정
share_rate_limit = get_rate_limit_decorator(f"{get_settings().rate_limit_share_per_minute}/minute")


@router.get(
    "/{token}",
    response_model=SharedAlbumResponse,
    summary="Access shared album",
)
@share_rate_limit
async def get_shared_album(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SharedAlbumResponse:
    """
    Access a shared album using a share link token.
    
    - **token**: The share link token (from the share URL)
    
    This endpoint does not require authentication.
    Returns the album with all photos including secure CDN URLs.
    
    The CDN URLs include auth tokens that expire after a configured time.
    """
    start_time = time.perf_counter()
    client_id = get_client_identifier(request)
    
    # 메트릭 수집: Rate limit 체크 요청 (허용됨)
    rate_limit_requests_total.labels(
        endpoint=request.url.path,
        status="allowed",
    ).inc()
    
    album_service = AlbumService(db)
    share_link = await album_service.get_share_link_by_token(token)
    
    # 메트릭 수집: 토큰 상태 확인
    if not share_link:
        # 무효한 토큰 (브루트포스 시도 가능성)
        share_link_access_total.labels(token_status="invalid", result="denied", access_type="shared").inc()
        share_link_brute_force_attempts.labels(client_id=client_id[:16]).inc()
        duration = time.perf_counter() - start_time
        share_link_access_duration_seconds.labels(token_status="invalid", result="denied", access_type="shared").observe(duration)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share link not found",
        )
    
    if not share_link.is_valid:
        # 만료된 토큰
        share_link_access_total.labels(token_status="expired", result="denied", access_type="shared").inc()
        duration = time.perf_counter() - start_time
        share_link_access_duration_seconds.labels(token_status="expired", result="denied", access_type="shared").observe(duration)
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Share link has expired or been deactivated",
        )
    
    # 유효한 토큰
    shared_album = await album_service.get_shared_album(share_link)
    
    if not shared_album:
        share_link_access_total.labels(token_status="valid", result="denied", access_type="shared").inc()
        duration = time.perf_counter() - start_time
        share_link_access_duration_seconds.labels(token_status="valid", result="denied", access_type="shared").observe(duration)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Album not found",
        )
    
    # 성공 — 앨범별 접속량(TOP 10 시각화용), 용량별 앨범 접근 시간
    share_link_access_total.labels(token_status="valid", result="success", access_type="shared").inc()
    share_link_access_by_album_total.labels(album_id=str(share_link.album_id), access_type="shared").inc()
    duration = time.perf_counter() - start_time
    share_link_access_duration_seconds.labels(token_status="valid", result="success", access_type="shared").observe(duration)
    album_access_duration_seconds.labels(
        size_bucket=album_access_size_bucket(shared_album.photo_count),
        access_type="shared",
    ).observe(duration)

    return shared_album


@router.get(
    "/{token}/photos/{photo_id}/image",
    summary="Shared album image (no auth); redirects to CDN when configured",
)
@share_rate_limit
async def get_shared_album_image(
    token: str,
    photo_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    공유 앨범 이미지 접근. **인증 불필요**. 공유 링크 유효 시 해당 앨범에 포함된 사진만 접근 가능.
    CDN 설정 시 짧은 유효기간 URL로 302 리다이렉트하여 트래픽이 LB를 거치지 않도록 함.
    """
    start = time.perf_counter()
    rate_limit_requests_total.labels(
        endpoint=request.url.path,
        status="allowed",
    ).inc()

    settings = get_settings()
    album_service = AlbumService(db)
    share_link = await album_service.get_share_link_by_token(token)

    token_status = "valid"
    if not share_link:
        token_status = "invalid"
        duration = time.perf_counter() - start
        share_link_image_access_total.labels(token_status="invalid", photo_in_album="no", access_type="shared").inc()
        image_access_total.labels(access_type="shared", result="denied").inc()
        image_access_duration_seconds.labels(access_type="shared", result="denied").observe(duration)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
    if not share_link.is_valid:
        token_status = "expired"
        duration = time.perf_counter() - start
        share_link_image_access_total.labels(token_status="expired", photo_in_album="no", access_type="shared").inc()
        image_access_total.labels(access_type="shared", result="denied").inc()
        image_access_duration_seconds.labels(access_type="shared", result="denied").observe(duration)
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Share link expired or inactive")

    album = share_link.album
    if not album:
        duration = time.perf_counter() - start
        share_link_image_access_total.labels(token_status=token_status, photo_in_album="no", access_type="shared").inc()
        image_access_total.labels(access_type="shared", result="denied").inc()
        image_access_duration_seconds.labels(access_type="shared", result="denied").observe(duration)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Album not found")

    photo = await album_service.get_photo_in_album(album.id, photo_id)
    if not photo:
        duration = time.perf_counter() - start
        share_link_image_access_total.labels(token_status=token_status, photo_in_album="no", access_type="shared").inc()
        image_access_total.labels(access_type="shared", result="denied").inc()
        image_access_duration_seconds.labels(access_type="shared", result="denied").observe(duration)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not in this album")

    share_link_image_access_total.labels(token_status=token_status, photo_in_album="yes", access_type="shared").inc()

    photo_service = PhotoService(db)
    if settings.nhn_cdn_domain and settings.nhn_cdn_app_key:
        cdn_url = await photo_service.cdn.generate_auth_token_url(
            photo.storage_path,
            expires_in=settings.share_image_token_expire_seconds,
            access_type="shared",
        )
        if cdn_url:
            duration = time.perf_counter() - start
            image_access_total.labels(access_type="shared", result="success").inc()
            image_access_duration_seconds.labels(access_type="shared", result="success").observe(duration)
            return RedirectResponse(url=cdn_url, status_code=status.HTTP_302_FOUND)
    try:
        file_content = await photo_service.download_photo(photo)
    except Exception as e:
        logger.error("Shared photo stream failed", exc_info=e, extra={"event": "share_stream", "photo_id": photo_id})
        duration = time.perf_counter() - start
        image_access_total.labels(access_type="shared", result="denied").inc()
        image_access_duration_seconds.labels(access_type="shared", result="denied").observe(duration)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load photo")
    duration = time.perf_counter() - start
    image_access_total.labels(access_type="shared", result="success").inc()
    image_access_duration_seconds.labels(access_type="shared", result="success").observe(duration)
    return Response(
        content=file_content,
        media_type=photo.content_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=60"},
    )
