"""
Photos router for photo management.
"""
import mimetypes
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.photo import (
    PhotoCreate,
    PhotoResponse,
    PhotoUpdate,
    PhotoWithUrl,
    PhotoUploadResponse,
)
from app.services.photo import PhotoService
from app.dependencies.auth import get_current_active_user

router = APIRouter(prefix="/photos", tags=["Photos"])

# Allowed content types for photo upload
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/heic",
    "image/heif",
}

# File extension to content type mapping
EXTENSION_TO_CONTENT_TYPE = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}

# Maximum file size (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


def guess_content_type(filename: str, provided_type: str = None) -> str:
    """
    Guess content type from filename or provided type.
    
    Args:
        filename: The filename
        provided_type: The content type provided by the client
        
    Returns:
        The content type, or None if cannot be determined
    """
    # If provided type is valid, use it
    if provided_type and provided_type in ALLOWED_CONTENT_TYPES:
        return provided_type
    
    # Try to guess from extension
    if filename:
        ext = filename.lower()
        # Check all possible extensions
        for ext_key, content_type in EXTENSION_TO_CONTENT_TYPE.items():
            if ext.endswith(ext_key):
                return content_type
        
        # Fallback to mimetypes module
        guessed_type, _ = mimetypes.guess_type(filename)
        if guessed_type and guessed_type in ALLOWED_CONTENT_TYPES:
            return guessed_type
    
    return provided_type


@router.post(
    "/",
    response_model=PhotoUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new photo",
)
async def upload_photo(
    file: UploadFile = File(..., description="Photo file to upload"),
    album_id: int = Form(..., description="Album ID to upload photo to"),
    title: str = Form(None, description="Optional photo title"),
    description: str = Form(None, description="Optional photo description"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PhotoUploadResponse:
    """
    Upload a new photo to the system.
    
    - **file**: Image file (JPEG, PNG, GIF, WebP, HEIC supported)
    - **album_id**: Album ID to upload photo to (required)
    - **title**: Optional title for the photo
    - **description**: Optional description
    
    The photo will be stored in NHN Cloud Object Storage with path: image/{album_id}/{filename}
    Maximum file size: 10MB
    """
    # Read file content first (needed for validation)
    content = await file.read()
    
    # Validate file size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB",
        )
    
    # Guess content type from filename if not provided or invalid
    content_type = guess_content_type(file.filename or "", file.content_type)
    
    # Validate content type
    if not content_type or content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: JPEG, PNG, GIF, WebP, HEIC. "
                   f"Provided: {file.content_type or 'unknown'}, "
                   f"Filename: {file.filename or 'unknown'}",
        )
    
    # Verify album exists and user has access
    from app.services.album import AlbumService
    album_service = AlbumService(db)
    album = await album_service.get_album_by_id(album_id, current_user.id)
    if not album:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Album with ID {album_id} not found or you don't have access to it.",
        )
    
    # Create metadata (handle empty strings)
    metadata = PhotoCreate(
        title=title.strip() if title and title.strip() else None,
        description=description.strip() if description and description.strip() else None,
    )
    
    # Upload photo
    photo_service = PhotoService(db)
    
    try:
        photo = await photo_service.upload_photo(
            user=current_user,
            album_id=album_id,
            file_content=content,
            filename=file.filename or "photo",
            content_type=content_type,
            metadata=metadata,
        )
        
        # Add photo to album
        await album_service.add_photos_to_album(album, [photo.id], current_user.id)
        await db.commit()
        
        # Generate CDN URL for the uploaded photo
        photo_with_url = await photo_service.get_photo_with_url(photo)
        
        return PhotoUploadResponse(
            id=photo.id,
            filename=photo.filename,
            original_filename=photo.original_filename,
            content_type=photo.content_type,
            file_size=photo.file_size,
            url=photo_with_url.url,
        )
        
    except ValueError as e:
        # ValueError는 이미 로그에 기록됨
        # 사용자 친화적인 에러 메시지만 반환 (내부 정보 노출 방지)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="사진 업로드에 실패했습니다. 잠시 후 다시 시도해주세요.",
        )
    except Exception as e:
        # 예외 로깅 (디버깅용)
        from app.services.nhn_logger import log_exception
        log_exception("Unexpected error during photo upload", e, user_id=current_user.id)
        # 다른 예외도 처리
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="사진 업로드에 실패했습니다. 잠시 후 다시 시도해주세요.",
        )


@router.get(
    "/",
    response_model=List[PhotoWithUrl],
    summary="Get user's photos",
)
async def get_photos(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[PhotoWithUrl]:
    """
    Get all photos for the current user with CDN URLs.
    
    - **skip**: Number of photos to skip (pagination)
    - **limit**: Maximum number of photos to return (max 100)
    
    Returns photos with secure CDN URLs that include auth tokens.
    """
    limit = min(limit, 100)  # Cap limit at 100
    
    photo_service = PhotoService(db)
    photos = await photo_service.get_user_photos(current_user.id, skip, limit)
    
    return await photo_service.get_photos_with_urls(photos)


@router.get(
    "/{photo_id}",
    response_model=PhotoWithUrl,
    summary="Get a specific photo",
)
async def get_photo(
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PhotoWithUrl:
    """
    Get a specific photo by ID with CDN URL.
    
    - **photo_id**: ID of the photo to retrieve
    
    Returns the photo with a secure CDN URL that includes an auth token.
    """
    photo_service = PhotoService(db)
    photo = await photo_service.get_photo_by_id(photo_id, current_user.id)
    
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )
    
    return await photo_service.get_photo_with_url(photo)


@router.patch(
    "/{photo_id}",
    response_model=PhotoResponse,
    summary="Update photo metadata",
)
async def update_photo(
    photo_id: int,
    update_data: PhotoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PhotoResponse:
    """
    Update a photo's metadata.
    
    - **photo_id**: ID of the photo to update
    - **title**: New title (optional)
    - **description**: New description (optional)
    """
    photo_service = PhotoService(db)
    photo = await photo_service.get_photo_by_id(photo_id, current_user.id)
    
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )
    
    updated_photo = await photo_service.update_photo(photo, update_data)
    return PhotoResponse.model_validate(updated_photo)


@router.get(
    "/{photo_id}/download",
    summary="Download a photo",
)
async def download_photo(
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Download a photo file.
    
    - **photo_id**: ID of the photo to download
    
    Returns the photo file as a downloadable attachment.
    """
    photo_service = PhotoService(db)
    photo = await photo_service.get_photo_by_id(photo_id, current_user.id)
    
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )
    
    try:
        # Download file from Object Storage
        file_content = await photo_service.download_photo(photo)
        
        # Determine filename
        filename = photo.original_filename or photo.filename
        if not filename or '.' not in filename:
            # Add extension based on content type
            ext_map = {
                'image/jpeg': '.jpg',
                'image/png': '.png',
                'image/gif': '.gif',
                'image/webp': '.webp',
                'image/heic': '.heic',
            }
            ext = ext_map.get(photo.content_type, '.jpg')
            filename = f"photo_{photo.id}{ext}"
        
        from fastapi.responses import Response
        return Response(
            content=file_content,
            media_type=photo.content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except Exception as e:
        from app.services.nhn_logger import log_exception
        log_exception("Failed to download photo", e, photo_id=photo_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download photo",
        )


@router.delete(
    "/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a photo",
)
async def delete_photo(
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Delete a photo from the system.
    
    - **photo_id**: ID of the photo to delete
    
    This will remove the photo from both the database and Object Storage.
    """
    photo_service = PhotoService(db)
    photo = await photo_service.get_photo_by_id(photo_id, current_user.id)
    
    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )
    
    await photo_service.delete_photo(photo)
