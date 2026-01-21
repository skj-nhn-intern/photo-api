"""
Share link model for public album sharing.
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, DateTime, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.album import Album


class ShareLink(Base):
    """
    Share link model for creating public access to albums.
    Users can create share links with optional expiration.
    """
    
    __tablename__ = "share_links"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    album_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("albums.id", ondelete="CASCADE"), nullable=False
    )
    
    # Unique share token (random string)
    token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    
    # Link settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    
    # Statistics
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    
    # Relationships
    album: Mapped["Album"] = relationship("Album", back_populates="share_links")
    
    @property
    def is_valid(self) -> bool:
        """Check if the share link is still valid."""
        if not self.is_active:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True
    
    def __repr__(self) -> str:
        return f"<ShareLink(id={self.id}, token={self.token[:8]}...)>"
