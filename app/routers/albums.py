"""
Albums router for album management.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.album import (
    AlbumCreate,
    AlbumResponse,
    AlbumUpdate,
    AlbumWithPhotos,
    AlbumPhotoAdd,
    AlbumPhotoRemove,
)
from app.schemas.share import ShareLinkCreate, ShareLinkResponse
from app.services.album import AlbumService
from app.dependencies.auth import get_current_active_user
from app.utils.prometheus_metrics import (
    album_operations_total,
    album_photo_operations_total,
    share_link_creation_total,
    albums_total,
    share_links_total,
)

router = APIRouter(prefix="/albums", tags=["Albums"])


@router.post(
    "/",
    response_model=AlbumResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new album",
)
async def create_album(
    album_data: AlbumCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AlbumResponse:
    """
    Create a new photo album.
    
    - **name**: Album name (required)
    - **description**: Optional album description
    """
    album_service = AlbumService(db)
    try:
        album = await album_service.create_album(current_user, album_data)
        
        # 메트릭 수집: 앨범 생성 성공
        album_operations_total.labels(operation="create", result="success").inc()
        
        # 비즈니스 메트릭 실시간 업데이트: 앨범 수
        albums_total.labels(type="total").inc()
        
        photo_count = await album_service.get_album_photo_count(album.id)
        
        return AlbumResponse(
            id=album.id,
            owner_id=album.owner_id,
            name=album.name,
            description=album.description,
            cover_photo_id=album.cover_photo_id,
            photo_count=photo_count,
            created_at=album.created_at,
            updated_at=album.updated_at,
        )
    except Exception as e:
        # 메트릭 수집: 앨범 생성 실패
        album_operations_total.labels(operation="create", result="failure").inc()
        raise


@router.get(
    "/",
    response_model=List[AlbumResponse],
    summary="Get user's albums",
)
async def get_albums(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[AlbumResponse]:
    """
    Get all albums for the current user.
    
    - **skip**: Number of albums to skip (pagination)
    - **limit**: Maximum number of albums to return (max 100)
    """
    limit = min(limit, 100)
    
    album_service = AlbumService(db)
    albums = await album_service.get_user_albums(current_user.id, skip, limit)
    
    result = []
    for album in albums:
        photo_count = await album_service.get_album_photo_count(album.id)
        result.append(AlbumResponse(
            id=album.id,
            owner_id=album.owner_id,
            name=album.name,
            description=album.description,
            cover_photo_id=album.cover_photo_id,
            photo_count=photo_count,
            created_at=album.created_at,
            updated_at=album.updated_at,
        ))
    
    return result


@router.get(
    "/{album_id}",
    response_model=AlbumWithPhotos,
    summary="Get album with photos",
)
async def get_album(
    album_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AlbumWithPhotos:
    """
    Get a specific album with all its photos.
    
    - **album_id**: ID of the album to retrieve
    
    Returns the album with all photos including secure CDN URLs.
    """
    album_service = AlbumService(db)
    album = await album_service.get_album_by_id(album_id, current_user.id)
    
    if not album:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Album not found",
        )
    
    return await album_service.get_album_with_photos(album)


@router.patch(
    "/{album_id}",
    response_model=AlbumResponse,
    summary="Update album",
)
async def update_album(
    album_id: int,
    update_data: AlbumUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AlbumResponse:
    """
    Update an album's metadata.
    
    - **album_id**: ID of the album to update
    - **name**: New album name (optional)
    - **description**: New description (optional)
    - **cover_photo_id**: ID of photo to use as cover (optional)
    """
    album_service = AlbumService(db)
    album = await album_service.get_album_by_id(album_id, current_user.id)
    
    if not album:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Album not found",
        )
    
    try:
        updated_album = await album_service.update_album(album, update_data)
        
        # 메트릭 수집: 앨범 수정 성공
        album_operations_total.labels(operation="update", result="success").inc()
        
        photo_count = await album_service.get_album_photo_count(updated_album.id)
        
        return AlbumResponse(
            id=updated_album.id,
            owner_id=updated_album.owner_id,
            name=updated_album.name,
            description=updated_album.description,
            cover_photo_id=updated_album.cover_photo_id,
            photo_count=photo_count,
            created_at=updated_album.created_at,
            updated_at=updated_album.updated_at,
        )
    except Exception as e:
        # 메트릭 수집: 앨범 수정 실패
        album_operations_total.labels(operation="update", result="failure").inc()
        raise


@router.delete(
    "/{album_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete album",
)
async def delete_album(
    album_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Delete an album.
    
    - **album_id**: ID of the album to delete
    
    Note: This only deletes the album, not the photos in it.
    """
    album_service = AlbumService(db)
    album = await album_service.get_album_by_id(album_id, current_user.id)
    
    if not album:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Album not found",
        )
    
    try:
        await album_service.delete_album(album)
        # 메트릭 수집: 앨범 삭제 성공
        album_operations_total.labels(operation="delete", result="success").inc()
    except Exception as e:
        # 메트릭 수집: 앨범 삭제 실패
        album_operations_total.labels(operation="delete", result="failure").inc()
        raise


# ============== Album Photos ==============


@router.post(
    "/{album_id}/photos",
    status_code=status.HTTP_200_OK,
    summary="Add photos to album",
)
async def add_photos_to_album(
    album_id: int,
    photo_data: AlbumPhotoAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Add photos to an album.
    
    - **album_id**: ID of the album
    - **photo_ids**: List of photo IDs to add
    
    Only photos owned by the current user can be added.
    """
    album_service = AlbumService(db)
    album = await album_service.get_album_by_id(album_id, current_user.id)
    
    if not album:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Album not found",
        )
    
    try:
        added = await album_service.add_photos_to_album(
            album, photo_data.photo_ids, current_user.id
        )
        
        # 메트릭 수집: 앨범에 사진 추가 성공
        album_photo_operations_total.labels(operation="add", result="success").inc()
        
        return {"message": f"{added} photo(s) added to album"}
    except Exception as e:
        # 메트릭 수집: 앨범에 사진 추가 실패
        album_photo_operations_total.labels(operation="add", result="failure").inc()
        raise


@router.delete(
    "/{album_id}/photos",
    status_code=status.HTTP_200_OK,
    summary="Remove photos from album",
)
async def remove_photos_from_album(
    album_id: int,
    photo_data: AlbumPhotoRemove,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Remove photos from an album.
    
    - **album_id**: ID of the album
    - **photo_ids**: List of photo IDs to remove
    
    Note: This only removes photos from the album, not from the system.
    """
    album_service = AlbumService(db)
    album = await album_service.get_album_by_id(album_id, current_user.id)
    
    if not album:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Album not found",
        )
    
    try:
        removed = await album_service.remove_photos_from_album(
            album, photo_data.photo_ids
        )
        
        # 메트릭 수집: 앨범에서 사진 제거 성공
        album_photo_operations_total.labels(operation="remove", result="success").inc()
        
        return {"message": f"{removed} photo(s) removed from album"}
    except Exception as e:
        # 메트릭 수집: 앨범에서 사진 제거 실패
        album_photo_operations_total.labels(operation="remove", result="failure").inc()
        raise


# ============== Share Links ==============


@router.post(
    "/{album_id}/share",
    response_model=ShareLinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create share link",
)
async def create_share_link(
    album_id: int,
    request: Request,
    share_data: ShareLinkCreate = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ShareLinkResponse:
    """
    Create a share link for an album.
    
    - **album_id**: ID of the album to share
    - **expires_in_days**: Number of days until the link expires (optional)
    
    Returns a share link that can be accessed without authentication.
    """
    album_service = AlbumService(db)
    album = await album_service.get_album_by_id(album_id, current_user.id)
    
    if not album:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Album not found",
        )
    
    # Create share data if not provided
    if share_data is None:
        share_data = ShareLinkCreate(album_id=album_id)
    else:
        share_data.album_id = album_id
    
    # Get base URL for share link
    base_url = str(request.base_url).rstrip("/")
    
    try:
        share_link = await album_service.create_share_link(album, share_data, base_url)
        
        # 메트릭 수집: 공유 링크 생성 성공
        share_link_creation_total.labels(result="success").inc()
        
        # 비즈니스 메트릭 실시간 업데이트: 공유 링크 수
        share_links_total.labels(status="total").inc()
        if share_link.is_active:
            share_links_total.labels(status="active").inc()
        
        return ShareLinkResponse(
            id=share_link.id,
            album_id=share_link.album_id,
            token=share_link.token,
            is_active=share_link.is_active,
            expires_at=share_link.expires_at,
            view_count=share_link.view_count,
            created_at=share_link.created_at,
            share_url=f"{base_url}/share/{share_link.token}",
        )
    except Exception as e:
        # 메트릭 수집: 공유 링크 생성 실패
        share_link_creation_total.labels(result="failure").inc()
        raise


@router.get(
    "/{album_id}/share",
    response_model=List[ShareLinkResponse],
    summary="Get album share links",
)
async def get_album_share_links(
    album_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[ShareLinkResponse]:
    """
    Get all share links for an album.
    
    - **album_id**: ID of the album
    """
    album_service = AlbumService(db)
    album = await album_service.get_album_by_id(album_id, current_user.id)
    
    if not album:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Album not found",
        )
    
    base_url = str(request.base_url).rstrip("/")
    share_links = await album_service.get_album_share_links(album_id)
    
    return [
        ShareLinkResponse(
            id=sl.id,
            album_id=sl.album_id,
            token=sl.token,
            is_active=sl.is_active,
            expires_at=sl.expires_at,
            view_count=sl.view_count,
            created_at=sl.created_at,
            share_url=f"{base_url}/share/{sl.token}",
        )
        for sl in share_links
    ]


@router.delete(
    "/{album_id}/share/{share_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete share link",
)
async def delete_share_link(
    album_id: int,
    share_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Delete a share link.
    
    - **album_id**: ID of the album
    - **share_id**: ID of the share link to delete
    """
    album_service = AlbumService(db)
    album = await album_service.get_album_by_id(album_id, current_user.id)
    
    if not album:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Album not found",
        )
    
    share_links = await album_service.get_album_share_links(album_id)
    share_link = next((sl for sl in share_links if sl.id == share_id), None)
    
    if not share_link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share link not found",
        )
    
    await album_service.delete_share_link(share_link)
