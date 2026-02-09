"""
Photos router for photo management.
"""
import logging
import mimetypes
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User

logger = logging.getLogger("app.photos")
from app.schemas.photo import (
    PhotoCreate,
    PhotoResponse,
    PhotoUpdate,
    PhotoWithUrl,
    PhotoUploadResponse,
    PresignedUrlRequest,
    PresignedUrlResponse,
    PhotoUploadConfirmRequest,
    PhotoUploadConfirmResponse,
)
from app.services.photo import PhotoService
from app.dependencies.auth import get_current_active_user
from app.utils.security import verify_image_access_token

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
    "/presigned-url",
    response_model=PresignedUrlResponse,
    status_code=status.HTTP_200_OK,
    summary="Get presigned URL for direct upload",
)
async def get_presigned_upload_url(
    request: PresignedUrlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PresignedUrlResponse:
    """
    Get a presigned URL for direct upload to Object Storage.
    
    이 방식을 사용하면 클라이언트가 서버를 거치지 않고 직접 Object Storage에 업로드할 수 있습니다.
    
    **사용 방법:**
    1. 이 엔드포인트를 호출하여 presigned URL을 받습니다.
    2. 받은 URL로 PUT 요청을 보내 파일을 직접 업로드합니다.
    3. 업로드 완료 후 `/photos/confirm` 엔드포인트를 호출하여 확인합니다.
    
    **업로드 예시 (JavaScript):**
    ```javascript
    // 1. Presigned URL 받기
    const response = await fetch('/photos/presigned-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            album_id: 1,
            filename: 'photo.jpg',
            content_type: 'image/jpeg',
            file_size: 1024000
        })
    });
    const data = await response.json();
    
    // 2. Object Storage에 직접 업로드
    await fetch(data.upload_url, {
        method: 'PUT',
        headers: { 'Content-Type': 'image/jpeg' },
        body: fileBlob
    });
    
    // 3. 업로드 완료 확인
    await fetch('/photos/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photo_id: data.photo_id })
    });
    ```
    
    참조: https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/s3-api-guide/
    """
    # Validate file size
    if request.file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB",
        )
    
    # Validate content type
    if request.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_CONTENT_TYPES)}",
        )
    
    # Verify album exists and user has access
    from app.services.album import AlbumService
    album_service = AlbumService(db)
    album = await album_service.get_album_by_id(request.album_id, current_user.id)
    if not album:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Album with ID {request.album_id} not found or you don't have access to it.",
        )
    
    # Create metadata
    metadata = PhotoCreate(
        title=request.title.strip() if request.title and request.title.strip() else None,
        description=request.description.strip() if request.description and request.description.strip() else None,
    )
    
    # Prepare upload
    photo_service = PhotoService(db)
    
    try:
        upload_data = await photo_service.prepare_photo_upload(
            user=current_user,
            album_id=request.album_id,
            filename=request.filename,
            content_type=request.content_type,
            file_size=request.file_size,
            metadata=metadata,
        )
        
        # Add photo to album
        await album_service.add_photos_to_album(album, [upload_data["photo_id"]], current_user.id)
        await db.commit()
        
        from app.config import get_settings
        settings = get_settings()
        
        return PresignedUrlResponse(
            photo_id=upload_data["photo_id"],
            upload_url=upload_data["upload_url"],
            object_key=upload_data["object_key"],
            expires_in=settings.nhn_s3_presigned_url_expire_seconds,
            upload_method=upload_data["upload_method"],
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Presigned URL generation failed", exc_info=e, extra={"event": "photo", "user_id": current_user.id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Presigned URL 생성에 실패했습니다. 잠시 후 다시 시도해주세요.",
        )


@router.post(
    "/confirm",
    response_model=PhotoUploadConfirmResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm photo upload completion",
)
async def confirm_photo_upload(
    request: PhotoUploadConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PhotoUploadConfirmResponse:
    """
    Confirm that a photo upload is complete.
    
    이 엔드포인트는 presigned URL을 사용하여 직접 업로드한 후 호출해야 합니다.
    업로드된 파일이 실제로 Object Storage에 존재하는지 확인합니다.
    
    - **photo_id**: `/photos/presigned-url`에서 받은 photo ID
    """
    photo_service = PhotoService(db)
    
    try:
        photo = await photo_service.confirm_photo_upload(
            photo_id=request.photo_id,
            user_id=current_user.id,
        )
        
        await db.commit()
        
        # Generate CDN URL for the uploaded photo
        photo_with_url = await photo_service.get_photo_with_url(photo)
        
        return PhotoUploadConfirmResponse(
            photo_id=photo.id,
            filename=photo.original_filename,
            url=photo_with_url.url,
            message="Photo upload confirmed successfully",
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Photo upload confirmation failed", exc_info=e, extra={"event": "photo", "user_id": current_user.id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="업로드 확인 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
        )


@router.post(
    "/",
    response_model=PhotoUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new photo (legacy direct upload)",
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
    Upload a new photo to the system (legacy method - 레거시 직접 업로드 방식).
    
    **권장 방법:** 대신 `/photos/presigned-url`을 사용하여 presigned URL 방식으로 업로드하세요.
    Presigned URL 방식은 서버 부하가 적고 업로드 속도가 빠릅니다.
    
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
        logger.error("Photo upload failed", exc_info=e, extra={"event": "photo", "user_id": current_user.id})
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
    "/{photo_id}/image",
    summary="Stream photo (proxy); requires short-lived token in query t=",
)
async def get_photo_image(
    photo_id: int,
    t: str = Query(..., description="Short-lived image access token"),
    db: AsyncSession = Depends(get_db),
):
    """
    이미지 바이트 스트림 반환. 쿼리 파라미터 t에 서명된 짧은 유효기간 토큰 필요.
    인가된 사용자에게만 목록 API에서 이 URL이 내려가므로, URL 유출 시에도 토큰 만료 후 접근 불가.
    """
    if not t:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    verified_id = verify_image_access_token(t)
    if verified_id is None or verified_id != photo_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired token")
    photo_service = PhotoService(db)
    photo = await photo_service.get_photo_by_id(photo_id, user_id=None)
    if not photo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
    try:
        file_content = await photo_service.download_photo(photo)
    except Exception as e:
        logger.error("Photo stream failed", exc_info=e, extra={"event": "photo", "photo_id": photo_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load photo",
        )
    from fastapi.responses import Response
    return Response(
        content=file_content,
        media_type=photo.content_type or "application/octet-stream",
        headers={
            "Cache-Control": "private, max-age=60",
        },
    )


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
        logger.error("Photo download failed", exc_info=e, extra={"event": "photo", "photo_id": photo_id})
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
