"""
Share link related Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict

from app.schemas.photo import PhotoWithUrl


class ShareLinkCreate(BaseModel):
    """Schema for creating a share link."""
    
    album_id: Optional[int] = None  # Set by router from URL parameter
    expires_in_days: Optional[int] = Field(
        None,
        ge=1,
        le=365,
        description="Number of days until the link expires (optional)"
    )


class ShareLinkResponse(BaseModel):
    """Schema for share link response."""
    
    id: int
    album_id: int
    token: str
    is_active: bool
    expires_at: Optional[datetime] = None
    view_count: int
    created_at: datetime
    share_url: str  # Full URL for sharing
    
    model_config = ConfigDict(from_attributes=True)


class SharedAlbumResponse(BaseModel):
    """
    Schema for shared album response (public access).
    Contains album info and photos with CDN URLs.
    """
    
    album_name: str
    album_description: Optional[str] = None
    photo_count: int
    photos: List[PhotoWithUrl] = []
    created_at: datetime


class ShareLinkUpdate(BaseModel):
    """Schema for updating a share link."""
    
    is_active: Optional[bool] = None
    expires_in_days: Optional[int] = Field(
        None,
        ge=1,
        le=365,
        description="Number of days until the link expires"
    )
