"""
Temp upload tracking model for presigned (Temp) URL upload detection and aggregation.

Records each presigned URL issuance (upload_id = photo_id, album_id, user_id, issued_at)
and completion (completed_at). Enables aggregation of "incomplete after TTL" counts.
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

if TYPE_CHECKING:
    pass


class TempUploadRecord(Base):
    """
    One record per presigned (Temp) URL issuance for upload tracking.

    - On presigned URL issue: insert row (upload_id=photo_id, album_id, user_id, issued_at, expires_at).
    - On upload confirm: set completed_at.
    - TTL expired and completed_at is null → count as "incomplete after TTL" for aggregation.
    """

    __tablename__ = "temp_upload_records"

    # upload_id is the same as photo_id (one-to-one with Photo created at presigned time)
    upload_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("photos.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    album_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<TempUploadRecord(upload_id={self.upload_id}, album_id={self.album_id}, "
            f"user_id={self.user_id}, completed_at={self.completed_at})>"
        )
