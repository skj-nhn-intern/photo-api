"""
Temp URL upload tracking service.

Records presigned URL issuance (upload_id, album_id, user_id, issued_at) in DB.
Marks completion on /photos/confirm. Enables aggregation of "incomplete after TTL" counts.
"""
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Dict

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.temp_upload import TempUploadRecord

logger = logging.getLogger("app.temp_upload_tracking")


async def record_issued(
    db: AsyncSession,
    upload_id: int,
    album_id: int,
    user_id: int,
    issued_at: datetime,
    expires_at: datetime,
) -> None:
    """
    Record a temp URL issuance. Call after successfully creating presigned URL.

    Writes to DB only.
    """
    record = TempUploadRecord(
        upload_id=upload_id,
        album_id=album_id,
        user_id=user_id,
        issued_at=issued_at,
        expires_at=expires_at,
        completed_at=None,
    )
    db.add(record)
    await db.flush()


async def mark_completed(db: AsyncSession, upload_id: int, completed_at: Optional[datetime] = None) -> bool:
    """
    Mark a temp upload as completed. Call after /photos/confirm success.

    Returns True if a record was found and updated.
    """
    if completed_at is None:
        completed_at = datetime.now(timezone.utc)

    result = await db.execute(
        select(TempUploadRecord).where(TempUploadRecord.upload_id == upload_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        return False
    record.completed_at = completed_at
    await db.flush()
    return True


async def get_incomplete_after_ttl(
    db: AsyncSession,
    now: Optional[datetime] = None,
    limit: int = 10_000,
) -> List[TempUploadRecord]:
    """
    Return records where temp URL has expired (expires_at < now) and upload was not completed.

    Used for aggregation: "TTL 만료 후에도 완료 안 된 건" → 미완료 집계.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    result = await db.execute(
        select(TempUploadRecord)
        .where(
            and_(
                TempUploadRecord.expires_at < now,
                TempUploadRecord.completed_at.is_(None),
            )
        )
        .order_by(TempUploadRecord.expires_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def aggregate_incomplete_after_ttl(
    db: AsyncSession,
    now: Optional[datetime] = None,
    limit: int = 50_000,
) -> Dict[str, Any]:
    """
    Aggregate incomplete uploads after TTL expiry.

    Returns:
        - total_count: number of records with expires_at < now and completed_at is null
        - by_user_id: { user_id: count }
        - by_album_id: { album_id: count }
        - sample_records: list of up to 100 sample records (upload_id, user_id, album_id, expires_at)
    """
    records = await get_incomplete_after_ttl(db, now=now, limit=limit)
    by_user: Dict[int, int] = {}
    by_album: Dict[int, int] = {}
    for r in records:
        by_user[r.user_id] = by_user.get(r.user_id, 0) + 1
        by_album[r.album_id] = by_album.get(r.album_id, 0) + 1

    sample = [
        {
            "upload_id": r.upload_id,
            "user_id": r.user_id,
            "album_id": r.album_id,
            "issued_at": r.issued_at.isoformat(),
            "expires_at": r.expires_at.isoformat(),
        }
        for r in records[:100]
    ]

    return {
        "total_count": len(records),
        "by_user_id": by_user,
        "by_album_id": by_album,
        "sample_records": sample,
    }
