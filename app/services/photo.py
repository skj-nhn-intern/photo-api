"""
Photo service for managing photos.
"""
from typing import List, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo
from app.models.user import User
from app.schemas.photo import PhotoCreate, PhotoUpdate, PhotoWithUrl
from app.services.nhn_object_storage import get_storage_service
from app.services.nhn_cdn import get_cdn_service
from app.services.nhn_logger import log_info, log_error, log_exception


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
            # Upload to Object Storage
            await self.storage.upload_file(
                file_content=file_content,
                object_name=storage_path,
                content_type=content_type,
            )
            
            log_info(
                "Photo uploaded to storage",
                user_id=user.id,
                storage_path=storage_path,
            )
            
        except Exception as e:
            log_exception("Failed to upload photo to storage", e, user_id=user.id)
            # 내부 에러 정보 노출 방지
            raise ValueError("사진 업로드에 실패했습니다. 잠시 후 다시 시도해주세요.")
        
        # Create photo record in database
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
        
        log_info(
            "Photo metadata saved",
            photo_id=photo.id,
            user_id=user.id,
        )
        
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
        
        log_info("Photo updated", photo_id=photo.id)
        
        return photo
    
    async def delete_photo(self, photo: Photo) -> bool:
        """
        Delete a photo from storage and database.
        
        Args:
            photo: Photo to delete
            
        Returns:
            True if deletion was successful
        """
        # Delete from Object Storage
        try:
            await self.storage.delete_file(photo.storage_path)
            log_info(
                "Photo deleted from storage",
                photo_id=photo.id,
                storage_path=photo.storage_path,
            )
        except Exception as e:
            log_exception(
                "Failed to delete photo from storage",
                e,
                photo_id=photo.id,
            )
            # Continue with database deletion even if storage deletion fails
        
        # Delete from database
        await self.db.delete(photo)
        await self.db.flush()
        
        log_info("Photo deleted from database", photo_id=photo.id)
        
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
            file_content = await self.storage.download_file(photo.storage_path)
            log_info(
                "Photo downloaded",
                photo_id=photo.id,
                storage_path=photo.storage_path,
                size=len(file_content),
            )
            return file_content
        except Exception as e:
            log_exception(
                "Failed to download photo",
                e,
                photo_id=photo.id,
                storage_path=photo.storage_path,
            )
            raise ValueError("사진 다운로드에 실패했습니다.")
    
    async def get_photo_with_url(self, photo: Photo) -> PhotoWithUrl:
        """
        Get photo response with CDN URL.
        
        Args:
            photo: Photo model
            
        Returns:
            PhotoWithUrl schema with CDN URL
        """
        cdn_url = await self.cdn.generate_auth_token_url(photo.storage_path)
        
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
            url=cdn_url,
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
