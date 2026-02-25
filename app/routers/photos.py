"""
Photos router for photo management.
"""
import logging
import mimetypes
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
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
from app.utils.prometheus_metrics import (
    image_access_total,
    image_access_duration_seconds,
    photo_upload_total,
    photo_upload_file_size_bytes,
    photo_upload_size_total,
    presigned_url_generation_total,
    photo_upload_confirm_total,
)
import time
from datetime import datetime, timezone, timedelta

from app.config import get_settings
from app.services.temp_upload_tracking import (
    record_issued,
    mark_completed,
    aggregate_incomplete_after_ttl,
)

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
    Get a Swift Temp URL for direct upload to Object Storage.
    
    클라이언트가 서버를 거치지 않고 직접 Object Storage에 업로드합니다.
    Swift API 경로를 사용하므로 컨테이너 CORS 설정이 적용되어 브라우저 OPTIONS preflight가 정상 동작합니다.
    
    **사용 방법:**
    1. 이 엔드포인트를 호출하여 업로드 URL을 받습니다.
    2. 받은 URL로 `upload_headers`와 함께 PUT 요청을 보내 파일을 직접 업로드합니다.
    3. 업로드 완료 후 `/photos/confirm` 엔드포인트를 호출하여 확인합니다.
    
    **업로드 예시 (JavaScript):**
    ```javascript
    // 1. 업로드 URL 받기
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
        headers: data.upload_headers,
        body: fileBlob
    });
    
    // 3. 업로드 완료 확인
    await fetch('/photos/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photo_id: data.photo_id })
    });
    ```
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

        # Temp URL 업로드 탐지: 발급 시 upload_id, 앨범ID, 유저ID, 발급시각 기록 (DB + 선택 Redis)
        settings = get_settings()
        issued_at = datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(seconds=settings.nhn_s3_presigned_url_expire_seconds)
        await record_issued(
            db,
            upload_id=upload_data["photo_id"],
            album_id=request.album_id,
            user_id=current_user.id,
            issued_at=issued_at,
            expires_at=expires_at,
        )

        await db.commit()

        # 메트릭 수집: Presigned URL 생성 성공
        presigned_url_generation_total.labels(result="success").inc()
        photo_upload_file_size_bytes.labels(upload_method="presigned").observe(request.file_size)

        return PresignedUrlResponse(
            photo_id=upload_data["photo_id"],
            upload_url=upload_data["upload_url"],
            object_key=upload_data["object_key"],
            expires_in=settings.nhn_s3_presigned_url_expire_seconds,
            upload_method=upload_data["upload_method"],
            upload_headers=upload_data.get("upload_headers", {}),
        )
        
    except ValueError as e:
        # 메트릭 수집: Presigned URL 생성 실패
        presigned_url_generation_total.labels(result="failure").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except Exception as e:
        # 메트릭 수집: Presigned URL 생성 실패
        presigned_url_generation_total.labels(result="failure").inc()
        logger.error("Presigned URL generation failed", exc_info=e, extra={"event": "photo_presigned", "user_id": current_user.id})
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
        
        # Temp URL 업로드 탐지: 완료 처리
        await mark_completed(db, upload_id=request.photo_id)

        await db.commit()

        # 메트릭 수집: 업로드 확인 성공, OBS 업로드 용량 추이
        photo_upload_confirm_total.labels(result="success").inc()
        photo_upload_total.labels(upload_method="presigned", result="success").inc()
        photo_upload_size_total.labels(user_id=str(current_user.id)).inc(photo.file_size)

        # Generate CDN URL for the uploaded photo
        photo_with_url = await photo_service.get_photo_with_url(photo)
        
        return PhotoUploadConfirmResponse(
            photo_id=photo.id,
            filename=photo.original_filename,
            url=photo_with_url.url,
            message="Photo upload confirmed successfully",
        )
        
    except ValueError as e:
        # 메트릭 수집: 업로드 확인 실패
        photo_upload_confirm_total.labels(result="failure").inc()
        photo_upload_total.labels(upload_method="presigned", result="failure").inc()
        logger.warning("Photo upload confirmation rejected", extra={"event": "photo_upload_confirm", "upload_id": request.photo_id, "user_id": current_user.id, "detail": str(e)})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        # 메트릭 수집: 업로드 확인 실패
        photo_upload_confirm_total.labels(result="failure").inc()
        photo_upload_total.labels(upload_method="presigned", result="failure").inc()
        logger.error("Photo upload confirmation failed", exc_info=e, extra={"event": "photo_upload_confirm", "upload_id": request.photo_id, "user_id": current_user.id})
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
    
    The photo will be stored in NHN Cloud Object Storage with path: photo/photo/image/{album_id}/{filename}
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
        
        # 메트릭 수집: 직접 업로드 성공, OBS 업로드 용량 추이
        photo_upload_total.labels(upload_method="direct", result="success").inc()
        photo_upload_file_size_bytes.labels(upload_method="direct").observe(len(content))
        photo_upload_size_total.labels(user_id=str(current_user.id)).inc(photo.file_size)

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
        # 메트릭 수집: 직접 업로드 실패
        photo_upload_total.labels(upload_method="direct", result="failure").inc()
        # ValueError는 이미 로그에 기록됨
        # 사용자 친화적인 에러 메시지만 반환 (내부 정보 노출 방지)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="사진 업로드에 실패했습니다. 잠시 후 다시 시도해주세요.",
        )
    except Exception as e:
        # 메트릭 수집: 직접 업로드 실패
        photo_upload_total.labels(upload_method="direct", result="failure").inc()
        logger.error("Photo upload failed", exc_info=e, extra={"event": "photo_upload", "user_id": current_user.id})
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
    "/upload-tracking",
    summary="Temp URL 업로드 추적 집계 (TTL 만료 후 confirm 없는 건)",
)
async def get_upload_tracking(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    TTL 만료 후에도 `POST /photos/confirm`이 호출되지 않은 Temp URL 업로드 건수를 집계합니다.

    - **total_count**: 미완료 건수
    - **by_user_id**, **by_album_id**: 구간별 건수
    - **sample_records**: 샘플 (최대 100건)

    상세: docs/TEMP-UPLOAD-AGGREGATION.md
    """
    return await aggregate_incomplete_after_ttl(db)


@router.get(
    "/{photo_id}/image",
    summary="Image access (JWT required); redirects to CDN when configured",
)
async def get_photo_image(
    photo_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    이미지 접근: **JWT 필수**. 권한 확인 후 CDN이 설정되어 있으면 짧은 유효기간 CDN URL로 302 리다이렉트하여
    이미지 트래픽이 로드밸런서/백엔드를 거치지 않도록 합니다. CDN이 없으면 바이트 스트림으로 반환합니다.

    **보안 보장:**
    - **인가**: Authorization: Bearer {JWT} 필요. 해당 사진의 **소유자**만 접근 가능.
    - **OBS URL 직접 접근 차단**: OBS가 public이어도, OBS URL을 직접 알더라도 접근 불가.
      CDN Auth Token이 없으면 CDN이 자동으로 거부합니다.
    - **링크만으로 접근 불가**: 이 엔드포인트는 JWT 없이 접근할 수 없습니다.
    
    **효율**: CDN 설정 시 302 리다이렉트 → 브라우저가 CDN에서 직접 다운로드 (LB 경유 없음).
    **클라이언트**: `<img>` 에서 쓰려면 `fetch('/photos/{id}/image', { headers: { Authorization } })` 후 blob URL 로 넣거나,
      같은 오리진 + 쿠키 인증을 사용하세요.
    """
    start_time = time.perf_counter()
    settings = get_settings()
    photo_service = PhotoService(db)
    photo = await photo_service.get_photo_by_id(photo_id, user_id=current_user.id)
    if not photo:
        # 소유자가 아님
        image_access_total.labels(access_type="authenticated", result="denied").inc()
        duration = time.perf_counter() - start_time
        image_access_duration_seconds.labels(access_type="authenticated", result="denied").observe(duration)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    # CDN Auth Token URL이 있으면 302 리다이렉트 (이미지 보기는 S3 GET presigned 미사용, CDN 토큰만)
    # ⚠️ 보안: OBS URL을 절대 반환하지 않음. CDN Auth Token이 포함된 URL만 반환.
    if settings.nhn_cdn_domain and settings.nhn_cdn_app_key:
        cdn_url = await photo_service.cdn.generate_auth_token_url(
            photo.storage_path,
            expires_in=settings.image_token_expire_seconds,
            access_type="authenticated",
        )
        if cdn_url:
            # 성공: CDN 리다이렉트
            image_access_total.labels(access_type="authenticated", result="success").inc()
            duration = time.perf_counter() - start_time
            image_access_duration_seconds.labels(access_type="authenticated", result="success").observe(duration)
            # CDN Auth Token이 포함된 URL만 반환 (토큰 없이는 CDN이 접근 거부)
            return RedirectResponse(url=cdn_url, status_code=status.HTTP_302_FOUND)
    # CDN 미설정 또는 토큰 실패 시: 백엔드 스트리밍
    # ⚠️ 보안: OBS URL을 절대 반환하지 않음. 백엔드를 통해 스트리밍하여 보안 보장.
    try:
        file_content = await photo_service.download_photo(photo)
        # 성공: 백엔드 스트리밍
        image_access_total.labels(access_type="authenticated", result="success").inc()
        duration = time.perf_counter() - start_time
        image_access_duration_seconds.labels(access_type="authenticated", result="success").observe(duration)
    except Exception as e:
        image_access_total.labels(access_type="authenticated", result="denied").inc()
        duration = time.perf_counter() - start_time
        image_access_duration_seconds.labels(access_type="authenticated", result="denied").observe(duration)
        logger.error("Photo stream failed", exc_info=e, extra={"event": "photo_stream", "photo_id": photo_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load photo",
        )
    return Response(
        content=file_content,
        media_type=photo.content_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=60"},
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
