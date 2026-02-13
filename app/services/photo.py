"""
Photo service for managing photos.
"""
import logging
from typing import List, Optional, Dict
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.photo import Photo
from app.models.user import User
from app.schemas.photo import PhotoCreate, PhotoUpdate, PhotoWithUrl
from app.services.nhn_object_storage import get_storage_service
from app.services.nhn_cdn import get_cdn_service
logger = logging.getLogger("app.photo")


class PhotoService:
    """
    Service for handling photo operations.
    Integrates with Object Storage for file storage and CDN for delivery.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = get_storage_service()
        self.cdn = get_cdn_service()
    
    async def upload_photo(
        self,
        user: User,
        album_id: int,
        file_content: bytes,
        filename: str,
        content_type: str,
        metadata: Optional[PhotoCreate] = None,
    ) -> Photo:
        """
        Upload a photo to Object Storage and save metadata to database.
        
        Args:
            user: Owner of the photo
            album_id: Album ID to upload photo to
            file_content: Photo file content as bytes
            filename: Original filename
            content_type: MIME type of the file
            metadata: Optional photo metadata
            
        Returns:
            Created Photo model
        """
        # Generate unique filename for storage
        file_ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
        unique_filename = f"{uuid.uuid4().hex}.{file_ext}" if file_ext else uuid.uuid4().hex
        # Storage path: image/{album_id}/{filename}
        storage_path = f"image/{album_id}/{unique_filename}"
        
        try:
            await self.storage.upload_file(
                file_content=file_content,
                object_name=storage_path,
                content_type=content_type,
            )
        except Exception as e:
            logger.error(
                "Photo upload failed",
                exc_info=e,
                extra={"event": "photo", "user_id": user.id, "path": storage_path},
            )
            raise ValueError("사진 업로드에 실패했습니다. 잠시 후 다시 시도해주세요.")
        
        photo = Photo(
            owner_id=user.id,
            filename=unique_filename,
            original_filename=filename,
            content_type=content_type,
            file_size=len(file_content),
            storage_path=storage_path,
            title=metadata.title if metadata else None,
            description=metadata.description if metadata else None,
        )
        
        self.db.add(photo)
        await self.db.flush()
        await self.db.refresh(photo)
        # 업로드 성공은 INFO (중요 비즈니스 이벤트)
        logger.info("Photo uploaded", extra={"event": "photo", "photo_id": photo.id, "user_id": user.id})
        return photo
    
    async def get_photo_by_id(
        self,
        photo_id: int,
        user_id: Optional[int] = None,
    ) -> Optional[Photo]:
        """
        Get a photo by ID.
        
        Args:
            photo_id: Photo ID
            user_id: If provided, only return if user owns the photo
            
        Returns:
            Photo if found (and owned by user if user_id provided), None otherwise
        """
        query = select(Photo).where(Photo.id == photo_id)
        
        if user_id is not None:
            query = query.where(Photo.owner_id == user_id)
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_user_photos(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Photo]:
        """
        Get all photos for a user.
        
        Args:
            user_id: User ID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of Photo models
        """
        result = await self.db.execute(
            select(Photo)
            .where(Photo.owner_id == user_id)
            .order_by(Photo.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def update_photo(
        self,
        photo: Photo,
        update_data: PhotoUpdate,
    ) -> Photo:
        """
        Update photo metadata.
        
        Args:
            photo: Photo to update
            update_data: Update data
            
        Returns:
            Updated Photo model
        """
        if update_data.title is not None:
            photo.title = update_data.title
        if update_data.description is not None:
            photo.description = update_data.description
        
        await self.db.flush()
        await self.db.refresh(photo)
        return photo
    
    async def delete_photo(self, photo: Photo) -> bool:
        """
        Delete a photo from storage and database.
        
        Args:
            photo: Photo to delete
            
        Returns:
            True if deletion was successful
        """
        try:
            await self.storage.delete_file(photo.storage_path)
        except Exception as e:
            # 스토리지 삭제 실패해도 DB에서는 삭제 (고아 파일 허용)
            logger.error(
                "Photo storage delete failed",
                exc_info=e,
                extra={"event": "photo", "photo_id": photo.id},
            )
        await self.db.delete(photo)
        await self.db.flush()
        # 삭제 성공은 로깅 안 함 (운영 노이즈 최소화)
        return True
    
    async def download_photo(self, photo: Photo) -> bytes:
        """
        Download a photo file from Object Storage.
        
        Args:
            photo: Photo model
            
        Returns:
            File content as bytes
        """
        try:
            return await self.storage.download_file(photo.storage_path)
        except Exception as e:
            logger.error(
                "Photo download failed",
                exc_info=e,
                extra={"event": "photo", "photo_id": photo.id},
            )
            raise ValueError("사진 다운로드에 실패했습니다.")
    
    async def get_photo_with_url(self, photo: Photo) -> PhotoWithUrl:
        """
        Get photo response with view URL.
        URL은 항상 /photos/{id}/image. 실제 이미지 접근 시 JWT 필요하며,
        서버가 권한 확인 후 CDN으로 302 리다이렉트하므로 트래픽은 LB를 거치지 않음.
        """
        url = f"/photos/{photo.id}/image"
        return PhotoWithUrl(
            id=photo.id,
            owner_id=photo.owner_id,
            filename=photo.filename,
            original_filename=photo.original_filename,
            content_type=photo.content_type,
            file_size=photo.file_size,
            title=photo.title,
            description=photo.description,
            created_at=photo.created_at,
            updated_at=photo.updated_at,
            url=url,
        )
    
    async def get_photos_with_urls(
        self,
        photos: List[Photo],
    ) -> List[PhotoWithUrl]:
        """
        Get multiple photos with CDN URLs.
        
        Args:
            photos: List of Photo models
            
        Returns:
            List of PhotoWithUrl schemas
        """
        return [await self.get_photo_with_url(photo) for photo in photos]
    
    async def prepare_photo_upload(
        self,
        user: User,
        album_id: int,
        filename: str,
        content_type: str,
        file_size: int,
        metadata: Optional[PhotoCreate] = None,
    ) -> Dict[str, any]:
        """
        Prepare a photo upload by generating presigned URL and creating photo record.
        
        Args:
            user: Owner of the photo
            album_id: Album ID to upload photo to
            filename: Original filename
            content_type: MIME type of the file
            file_size: File size in bytes
            metadata: Optional photo metadata
            
        Returns:
            Dictionary with photo_id, upload_url, and object_key
        """
        # Generate unique filename for storage
        file_ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
        unique_filename = f"{uuid.uuid4().hex}.{file_ext}" if file_ext else uuid.uuid4().hex
        # Storage path: image/{album_id}/{filename}
        storage_path = f"image/{album_id}/{unique_filename}"
        
        # Create photo record in database (pending upload)
        photo = Photo(
            owner_id=user.id,
            filename=unique_filename,
            original_filename=filename,
            content_type=content_type,
            file_size=file_size,
            storage_path=storage_path,
            title=metadata.title if metadata else None,
            description=metadata.description if metadata else None,
        )
        
        self.db.add(photo)
        await self.db.flush()
        await self.db.refresh(photo)
        
        # Generate presigned POST URL (multipart/form-data → CORS simple request → OPTIONS 없음)
        try:
            presigned_data = self.storage.generate_presigned_upload_url(
                object_name=storage_path,
                content_type=content_type,
            )
            
            logger.info(
                "Presigned POST generated",
                extra={"event": "photo", "photo_id": photo.id, "user_id": user.id}
            )
            
            return {
                "photo_id": photo.id,
                "upload_url": presigned_data["url"],
                "upload_method": presigned_data["method"],
                "upload_fields": presigned_data.get("fields", {}),
                "object_key": storage_path,
            }
            
        except Exception as e:
            # If presigned URL generation fails, delete the photo record
            await self.db.delete(photo)
            await self.db.flush()
            logger.error(
                "Presigned URL generation failed",
                exc_info=e,
                extra={"event": "photo", "user_id": user.id},
            )
            raise ValueError("Presigned URL 생성에 실패했습니다. 잠시 후 다시 시도해주세요.")
    
    async def confirm_photo_upload(
        self,
        photo_id: int,
        user_id: int,
    ) -> Photo:
        """
        Confirm that a photo upload is complete by verifying the file exists in storage.
        
        Args:
            photo_id: Photo ID to confirm
            user_id: User ID (for ownership verification)
            
        Returns:
            Confirmed Photo model
            
        Raises:
            ValueError: If photo not found, not owned by user, or file doesn't exist
        """
        # Get photo from database
        photo = await self.get_photo_by_id(photo_id, user_id)
        if not photo:
            raise ValueError("사진을 찾을 수 없거나 접근 권한이 없습니다.")
        
        # Verify file exists in storage
        try:
            file_exists = await self.storage.file_exists(photo.storage_path)
            if not file_exists:
                logger.error(
                    "Photo upload verification failed - file not found",
                    extra={"event": "photo", "photo_id": photo_id, "user_id": user_id}
                )
                raise ValueError("업로드된 파일을 찾을 수 없습니다. 업로드를 다시 시도해주세요.")
            
            logger.info(
                "Photo upload confirmed",
                extra={"event": "photo", "photo_id": photo_id, "user_id": user_id}
            )
            
            return photo
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(
                "Photo upload verification failed",
                exc_info=e,
                extra={"event": "photo", "photo_id": photo_id, "user_id": user_id}
            )
            raise ValueError("파일 확인 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")