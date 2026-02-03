"""
Album service for managing albums and shared links.
"""
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.album import Album, AlbumPhoto
from app.models.photo import Photo
from app.models.share import ShareLink
from app.models.user import User
from app.schemas.album import AlbumCreate, AlbumUpdate, AlbumWithPhotos
from app.schemas.share import ShareLinkCreate, ShareLinkResponse, SharedAlbumResponse
from app.services.photo import PhotoService
from app.services.nhn_logger import log_info, log_error
from app.utils.security import generate_share_token
from app.config import get_settings

settings = get_settings()


class AlbumService:
    """
    Service for handling album operations.
    Includes album CRUD and share link management.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.photo_service = PhotoService(db)
    
    # ============== Album CRUD ==============
    
    async def create_album(
        self,
        user: User,
        album_data: AlbumCreate,
    ) -> Album:
        """
        Create a new album.
        
        Args:
            user: Owner of the album
            album_data: Album creation data
            
        Returns:
            Created Album model
        """
        album = Album(
            owner_id=user.id,
            name=album_data.name,
            description=album_data.description,
        )
        
        self.db.add(album)
        await self.db.flush()
        await self.db.refresh(album)
        return album
    
    async def get_album_by_id(
        self,
        album_id: int,
        user_id: Optional[int] = None,
    ) -> Optional[Album]:
        """
        Get an album by ID.
        
        Args:
            album_id: Album ID
            user_id: If provided, only return if user owns the album
            
        Returns:
            Album if found, None otherwise
        """
        query = select(Album).where(Album.id == album_id)
        
        if user_id is not None:
            query = query.where(Album.owner_id == user_id)
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_user_albums(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Album]:
        """
        Get all albums for a user.
        
        Args:
            user_id: User ID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of Album models
        """
        result = await self.db.execute(
            select(Album)
            .where(Album.owner_id == user_id)
            .order_by(Album.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_album_photo_count(self, album_id: int) -> int:
        """Get the number of photos in an album."""
        result = await self.db.execute(
            select(func.count(AlbumPhoto.id))
            .where(AlbumPhoto.album_id == album_id)
        )
        return result.scalar() or 0
    
    async def update_album(
        self,
        album: Album,
        update_data: AlbumUpdate,
    ) -> Album:
        """
        Update album metadata.
        
        Args:
            album: Album to update
            update_data: Update data
            
        Returns:
            Updated Album model
        """
        if update_data.name is not None:
            # 빈 문자열을 None으로 변환하지 않음 (name은 필수 필드이므로)
            album.name = update_data.name
        if update_data.description is not None:
            # 빈 문자열을 None으로 변환하여 description을 지울 수 있도록 함
            if isinstance(update_data.description, str) and not update_data.description.strip():
                album.description = None
            else:
                album.description = update_data.description
        if update_data.cover_photo_id is not None:
            album.cover_photo_id = update_data.cover_photo_id
        
        await self.db.flush()
        await self.db.refresh(album)
        return album
    
    async def delete_album(self, album: Album) -> bool:
        """
        Delete an album.
        
        Args:
            album: Album to delete
            
        Returns:
            True if deletion was successful
        """
        await self.db.delete(album)
        await self.db.flush()
        return True
    
    # ============== Album Photos ==============
    
    async def add_photos_to_album(
        self,
        album: Album,
        photo_ids: List[int],
        user_id: int,
    ) -> int:
        """
        Add photos to an album.
        
        Args:
            album: Album to add photos to
            photo_ids: List of photo IDs to add
            user_id: User ID (for permission check)
            
        Returns:
            Number of photos added
        """
        # Get photos owned by user
        result = await self.db.execute(
            select(Photo)
            .where(Photo.id.in_(photo_ids))
            .where(Photo.owner_id == user_id)
        )
        photos = list(result.scalars().all())
        
        if not photos:
            return 0
        
        # Get existing album photos
        existing = await self.db.execute(
            select(AlbumPhoto.photo_id)
            .where(AlbumPhoto.album_id == album.id)
        )
        existing_ids = set(row[0] for row in existing.all())
        
        # Add new photos
        added = 0
        max_order = await self._get_max_order(album.id)
        
        for photo in photos:
            if photo.id not in existing_ids:
                album_photo = AlbumPhoto(
                    album_id=album.id,
                    photo_id=photo.id,
                    order=max_order + added + 1,
                )
                self.db.add(album_photo)
                added += 1
        
        await self.db.flush()
        return added
    
    async def remove_photos_from_album(
        self,
        album: Album,
        photo_ids: List[int],
    ) -> int:
        """
        Remove photos from an album.
        
        Args:
            album: Album to remove photos from
            photo_ids: List of photo IDs to remove
            
        Returns:
            Number of photos removed
        """
        result = await self.db.execute(
            select(AlbumPhoto)
            .where(AlbumPhoto.album_id == album.id)
            .where(AlbumPhoto.photo_id.in_(photo_ids))
        )
        album_photos = list(result.scalars().all())
        
        for ap in album_photos:
            await self.db.delete(ap)
        
        await self.db.flush()
        return len(album_photos)
    
    async def get_album_photos(self, album_id: int) -> List[Photo]:
        """
        Get all photos in an album.
        
        Args:
            album_id: Album ID
            
        Returns:
            List of Photo models ordered by album order
        """
        result = await self.db.execute(
            select(Photo)
            .join(AlbumPhoto, AlbumPhoto.photo_id == Photo.id)
            .where(AlbumPhoto.album_id == album_id)
            .order_by(AlbumPhoto.order)
        )
        return list(result.scalars().all())
    
    async def _get_max_order(self, album_id: int) -> int:
        """Get the maximum order value in an album."""
        result = await self.db.execute(
            select(func.max(AlbumPhoto.order))
            .where(AlbumPhoto.album_id == album_id)
        )
        return result.scalar() or 0
    
    async def get_album_with_photos(self, album: Album) -> AlbumWithPhotos:
        """
        Get album with photos including CDN URLs.
        
        Args:
            album: Album model
            
        Returns:
            AlbumWithPhotos schema
        """
        photos = await self.get_album_photos(album.id)
        photos_with_urls = await self.photo_service.get_photos_with_urls(photos)
        photo_count = len(photos)
        
        return AlbumWithPhotos(
            id=album.id,
            owner_id=album.owner_id,
            name=album.name,
            description=album.description,
            cover_photo_id=album.cover_photo_id,
            photo_count=photo_count,
            created_at=album.created_at,
            updated_at=album.updated_at,
            photos=photos_with_urls,
        )
    
    # ============== Share Links ==============
    
    async def create_share_link(
        self,
        album: Album,
        share_data: ShareLinkCreate,
        base_url: str = "",
    ) -> ShareLink:
        """
        Create a share link for an album.
        
        Args:
            album: Album to share
            share_data: Share link creation data
            base_url: Base URL for constructing full share URL
            
        Returns:
            Created ShareLink model
        """
        # Generate unique token
        token = generate_share_token()
        
        # Calculate expiration
        expires_at = None
        if share_data.expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=share_data.expires_in_days)
        
        share_link = ShareLink(
            album_id=album.id,
            token=token,
            expires_at=expires_at,
        )
        
        self.db.add(share_link)
        await self.db.flush()
        await self.db.refresh(share_link)
        log_info("Share link created", event="share", share_id=share_link.id, album_id=album.id)
        return share_link
    
    async def get_share_link_by_token(
        self,
        token: str,
    ) -> Optional[ShareLink]:
        """
        Get a share link by token.
        
        Args:
            token: Share link token
            
        Returns:
            ShareLink if found, None otherwise
        """
        result = await self.db.execute(
            select(ShareLink)
            .where(ShareLink.token == token)
            .options(selectinload(ShareLink.album))
        )
        return result.scalar_one_or_none()
    
    async def get_album_share_links(
        self,
        album_id: int,
    ) -> List[ShareLink]:
        """
        Get all share links for an album.
        
        Args:
            album_id: Album ID
            
        Returns:
            List of ShareLink models
        """
        result = await self.db.execute(
            select(ShareLink)
            .where(ShareLink.album_id == album_id)
            .order_by(ShareLink.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def deactivate_share_link(
        self,
        share_link: ShareLink,
    ) -> ShareLink:
        """
        Deactivate a share link.
        
        Args:
            share_link: ShareLink to deactivate
            
        Returns:
            Updated ShareLink model
        """
        share_link.is_active = False
        await self.db.flush()
        await self.db.refresh(share_link)
        return share_link
    
    async def delete_share_link(
        self,
        share_link: ShareLink,
    ) -> bool:
        """
        Delete a share link.
        
        Args:
            share_link: ShareLink to delete
            
        Returns:
            True if deletion was successful
        """
        await self.db.delete(share_link)
        await self.db.flush()
        return True
    
    async def increment_view_count(
        self,
        share_link: ShareLink,
    ) -> None:
        """Increment the view count of a share link."""
        share_link.view_count += 1
        await self.db.flush()
    
    async def get_shared_album(
        self,
        share_link: ShareLink,
    ) -> Optional[SharedAlbumResponse]:
        """
        Get shared album data for public access.
        
        Args:
            share_link: ShareLink model
            
        Returns:
            SharedAlbumResponse if valid, None otherwise
        """
        if not share_link.is_valid:
            log_error("Share access denied", event="share", share_id=share_link.id)
            return None
        
        # Get album
        album = share_link.album
        if not album:
            return None
        
        # Get photos with CDN URLs
        photos = await self.get_album_photos(album.id)
        photos_with_urls = await self.photo_service.get_photos_with_urls(photos)
        
        await self.increment_view_count(share_link)
        return SharedAlbumResponse(
            album_name=album.name,
            album_description=album.description,
            photo_count=len(photos),
            photos=photos_with_urls,
            created_at=album.created_at,
        )
