"""
Share router for public album access.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.schemas.share import SharedAlbumResponse
from app.services.album import AlbumService
from app.services.photo import PhotoService

logger = logging.getLogger("app.share")
router = APIRouter(prefix="/share", tags=["Shared Albums"])


@router.get(
    "/{token}",
    response_model=SharedAlbumResponse,
    summary="Access shared album",
)
async def get_shared_album(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> SharedAlbumResponse:
    """
    Access a shared album using a share link token.
    
    - **token**: The share link token (from the share URL)
    
    This endpoint does not require authentication.
    Returns the album with all photos including secure CDN URLs.
    
    The CDN URLs include auth tokens that expire after a configured time.
    """
    album_service = AlbumService(db)
    share_link = await album_service.get_share_link_by_token(token)
    
    if not share_link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share link not found",
        )
    
    if not share_link.is_valid:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Share link has expired or been deactivated",
        )
    
    shared_album = await album_service.get_shared_album(share_link)
    
    if not shared_album:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Album not found",
        )
    
    return shared_album


@router.get(
    "/{token}/photos/{photo_id}/image",
    summary="Shared album image (no auth); redirects to CDN when configured",
)
async def get_shared_album_image(
    token: str,
    photo_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    공유 앨범 이미지 접근. **인증 불필요**. 공유 링크 유효 시 해당 앨범에 포함된 사진만 접근 가능.
    CDN 설정 시 짧은 유효기간 URL로 302 리다이렉트하여 트래픽이 LB를 거치지 않도록 함.
    """
    settings = get_settings()
    album_service = AlbumService(db)
    share_link = await album_service.get_share_link_by_token(token)
    if not share_link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
    if not share_link.is_valid:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Share link expired or inactive")
    album = share_link.album
    if not album:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Album not found")

    photo = await album_service.get_photo_in_album(album.id, photo_id)
    if not photo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not in this album")

    photo_service = PhotoService(db)
    if settings.nhn_cdn_domain and settings.nhn_cdn_app_key:
        cdn_url = await photo_service.cdn.generate_auth_token_url(
            photo.storage_path,
            expires_in=settings.image_token_expire_seconds,
        )
        if cdn_url:
            return RedirectResponse(url=cdn_url, status_code=status.HTTP_302_FOUND)
    try:
        file_content = await photo_service.download_photo(photo)
    except Exception as e:
        logger.error("Shared photo stream failed", exc_info=e, extra={"event": "share", "photo_id": photo_id})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load photo")
    return Response(
        content=file_content,
        media_type=photo.content_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=60"},
    )
