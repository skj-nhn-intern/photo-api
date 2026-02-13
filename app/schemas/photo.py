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


class PresignedUrlRequest(BaseModel):
    """Schema for requesting a presigned URL."""
    
    album_id: int = Field(..., description="Album ID to upload photo to")
    filename: str = Field(..., description="Original filename", max_length=255)
    content_type: str = Field(..., description="MIME type of the file")
    file_size: int = Field(..., description="File size in bytes", gt=0)
    title: Optional[str] = Field(None, max_length=255, description="Optional photo title")
    description: Optional[str] = Field(None, description="Optional photo description")


class PresignedUrlResponse(BaseModel):
    """Schema for upload URL response (Swift Temp URL)."""
    
    photo_id: int = Field(..., description="Photo ID for tracking upload")
    upload_url: str = Field(..., description="PUT 요청을 보낼 Temp URL")
    object_key: str = Field(..., description="Object key in storage")
    expires_in: int = Field(..., description="URL expiration time in seconds")
    upload_method: str = Field(default="PUT", description="HTTP method")
    upload_headers: dict = Field(
        default_factory=dict,
        description="PUT 요청 시 사용할 헤더 (Content-Type 등).",
    )


class PhotoUploadConfirmRequest(BaseModel):
    """Schema for confirming photo upload completion."""
    
    photo_id: int = Field(..., description="Photo ID to confirm")


class PhotoUploadConfirmResponse(BaseModel):
    """Schema for upload confirmation response."""
    
    photo_id: int
    filename: str
    url: Optional[str] = None  # CDN URL with auth token
    message: str = "Photo upload confirmed successfully"
