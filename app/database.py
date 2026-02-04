"""
Database configuration and session management.
Uses async SQLAlchemy for non-blocking database operations.
Implements proper connection pooling to prevent memory leaks.

로깅 최적화:
- SQL echo 비활성화 (운영 노이즈 방지)
- 느린 쿼리 로깅 (1초 이상)
- 커넥션 풀 에러 로깅
"""
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, QueuePool

from app.config import get_settings
from app.utils.prometheus_metrics import db_errors_total

_logger = logging.getLogger("app.db")

settings = get_settings()

# 느린 쿼리 임계값 (초)
SLOW_QUERY_THRESHOLD = 1.0


# Create async engine - echo는 항상 False (로그 노이즈 방지)
if "sqlite" in settings.database_url:
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        poolclass=NullPool,
    )
else:
    engine = create_async_engine(
        settings.database_url,
        echo=False,  # SQL 로그 비활성화
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )


# 느린 쿼리 로깅
@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("query_start_time", []).append(time.perf_counter())


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    start_times = conn.info.get("query_start_time")
    if start_times:
        elapsed = time.perf_counter() - start_times.pop()
        if elapsed >= SLOW_QUERY_THRESHOLD:
            # 쿼리 앞 100자만 로깅 (보안/가독성)
            short_stmt = statement[:100] + "..." if len(statement) > 100 else statement
            _logger.warning(
                "Slow query",
                extra={"event": "db", "ms": round(elapsed * 1000), "query": short_stmt},
            )


# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


async def init_db() -> None:
    """Initialize database by creating all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections properly."""
    await engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session.
    Ensures proper cleanup of connections after each request.

    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            db_errors_total.inc()
            _logger.error(
                "DB error",
                extra={
                    "event": "db",
                    "error_type": type(e).__name__,
                    "error": str(e)[:200],  # 에러 메시지 앞 200자
                },
            )
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions outside of request context.
    Useful for background tasks or CLI commands.
    
    Usage:
        async with get_db_context() as session:
            result = await session.execute(query)
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            _logger.error(
                "DB context error",
                extra={
                    "event": "db",
                    "error_type": type(e).__name__,
                    "error": str(e)[:200],
                },
            )
            await session.rollback()
            raise
        finally:
            await session.close()
