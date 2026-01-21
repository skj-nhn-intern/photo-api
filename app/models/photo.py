"""
Photo model for storing photo metadata.
Actual photo files are stored in NHN Cloud Object Storage.
"""
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.album import AlbumPhoto


class Photo(Base):
    """
    Photo model for storing photo metadata.
    The actual image file is stored in Object Storage.
    """
    
    __tablename__ = "photos"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    
    # File metadata
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Storage information
    storage_path: Mapped[str] = mapped_column(
        String(500), nullable=False, index=True
    )
    
    # Optional metadata
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="photos")
    album_associations: Mapped[List["AlbumPhoto"]] = relationship(
        "AlbumPhoto", back_populates="photo", cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Photo(id={self.id}, filename={self.filename})>"
