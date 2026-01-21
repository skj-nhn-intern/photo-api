"""
Album-related Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict

from app.schemas.photo import PhotoWithUrl


class AlbumBase(BaseModel):
    """Base schema with common album attributes."""
    
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class AlbumCreate(AlbumBase):
    """Schema for album creation."""
    
    pass


class AlbumUpdate(BaseModel):
    """Schema for updating album."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    cover_photo_id: Optional[int] = None


class AlbumResponse(AlbumBase):
    """Schema for album response."""
    
    id: int
    owner_id: int
    cover_photo_id: Optional[int] = None
    photo_count: int = 0
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class AlbumWithPhotos(AlbumResponse):
    """Schema for album response with photos included."""
    
    photos: List[PhotoWithUrl] = []


class AlbumPhotoAdd(BaseModel):
    """Schema for adding photos to an album."""
    
    photo_ids: List[int] = Field(..., min_length=1)


class AlbumPhotoRemove(BaseModel):
    """Schema for removing photos from an album."""
    
    photo_ids: List[int] = Field(..., min_length=1)


class AlbumPhotoReorder(BaseModel):
    """Schema for reordering photos in an album."""
    
    photo_orders: List[dict] = Field(
        ...,
        description="List of {photo_id: int, order: int} objects"
    )
