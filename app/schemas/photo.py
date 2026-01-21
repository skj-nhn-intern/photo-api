"""
Photo-related Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class PhotoBase(BaseModel):
    """Base schema with common photo attributes."""
    
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None


class PhotoCreate(PhotoBase):
    """Schema for photo creation metadata (file uploaded separately)."""
    
    pass


class PhotoUpdate(PhotoBase):
    """Schema for updating photo metadata."""
    
    pass


class PhotoResponse(PhotoBase):
    """Schema for photo response."""
    
    id: int
    owner_id: int
    filename: str
    original_filename: str
    content_type: str
    file_size: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class PhotoWithUrl(PhotoResponse):
    """
    Schema for photo response with CDN URL.
    The URL includes auth token for secure access.
    """
    
    url: str  # CDN URL with auth token


class PhotoUploadResponse(BaseModel):
    """Schema for photo upload response."""
    
    id: int
    filename: str
    original_filename: str
    content_type: str
    file_size: int
    url: Optional[str] = None  # CDN URL with auth token
    message: str = "Photo uploaded successfully"
    
    model_config = ConfigDict(from_attributes=True)
