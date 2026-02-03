"""
Database configuration and session management.
Uses async SQLAlchemy for non-blocking database operations.
Implements proper connection pooling to prevent memory leaks.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, QueuePool

from app.config import get_settings
from app.utils.prometheus_metrics import db_errors_total

# 표준 logging 사용 (nhn_logger import 시 models → database 순환 참조 방지)
_logger = logging.getLogger("app")

settings = get_settings()


# Create async engine with proper pool configuration
# Using QueuePool for connection pooling to prevent connection leaks
if "sqlite" in settings.database_url:
    # SQLite doesn't support connection pooling well with async
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        poolclass=NullPool,  # Disable pooling for SQLite
    )
else:
    # PostgreSQL or other databases - use connection pool
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        poolclass=QueuePool,
        pool_size=5,  # Number of connections to keep open
        max_overflow=10,  # Max additional connections
        pool_timeout=30,  # Timeout waiting for connection
        pool_recycle=1800,  # Recycle connections after 30 minutes
        pool_pre_ping=True,  # Verify connections before use
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
        except Exception:
            db_errors_total.inc()
            _logger.exception("Database session failed", exc_info=True, extra={"event": "db"})
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
        except Exception:
            _logger.exception("Database context failed", exc_info=True, extra={"event": "db"})
            await session.rollback()
            raise
        finally:
            await session.close()
