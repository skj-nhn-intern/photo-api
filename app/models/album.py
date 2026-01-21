"""
Album model for organizing photos into collections.
"""
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.photo import Photo
    from app.models.share import ShareLink


class Album(Base):
    """Album model for grouping photos together."""
    
    __tablename__ = "albums"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    
    # Album information
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Cover photo (optional)
    cover_photo_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("photos.id", ondelete="SET NULL"), nullable=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="albums")
    photo_associations: Mapped[List["AlbumPhoto"]] = relationship(
        "AlbumPhoto", back_populates="album", cascade="all, delete-orphan"
    )
    share_links: Mapped[List["ShareLink"]] = relationship(
        "ShareLink", back_populates="album", cascade="all, delete-orphan"
    )
    cover_photo: Mapped[Optional["Photo"]] = relationship(
        "Photo", foreign_keys=[cover_photo_id]
    )
    
    def __repr__(self) -> str:
        return f"<Album(id={self.id}, name={self.name})>"


class AlbumPhoto(Base):
    """
    Association table between Album and Photo.
    Allows many-to-many relationship with additional metadata.
    """
    
    __tablename__ = "album_photos"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    album_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("albums.id", ondelete="CASCADE"), nullable=False
    )
    photo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("photos.id", ondelete="CASCADE"), nullable=False
    )
    
    # Order within the album
    order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamp
    added_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    
    # Relationships
    album: Mapped["Album"] = relationship(
        "Album", back_populates="photo_associations"
    )
    photo: Mapped["Photo"] = relationship(
        "Photo", back_populates="album_associations"
    )
    
    def __repr__(self) -> str:
        return f"<AlbumPhoto(album_id={self.album_id}, photo_id={self.photo_id})>"
