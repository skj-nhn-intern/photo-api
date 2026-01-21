"""
Share router for public album access.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.share import SharedAlbumResponse
from app.services.album import AlbumService

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
