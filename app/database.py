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
from app.utils.prometheus_metrics import db_errors_total, REGISTRY, Gauge

_logger = logging.getLogger("app.db")

# DB 연결 풀 모니터링 메트릭
db_pool_active_connections = Gauge(
    "photo_api_db_pool_active_connections",
    "Number of active database connections in pool",
    registry=REGISTRY,
)

db_pool_waiting_requests = Gauge(
    "photo_api_db_pool_waiting_requests",
    "Number of requests waiting for database connection",
    registry=REGISTRY,
)

settings = get_settings()

# 느린 쿼리 임계값 (초)
SLOW_QUERY_THRESHOLD = 1.0

# CI/이미지 검증 시 DATABASE_URL이 비어 있을 수 있음 — 빈 값이면 SQLite 기본 사용
_database_url = (settings.database_url or "").strip()
if not _database_url:
    _database_url = "sqlite+aiosqlite:///./photo_api.db"

# Create async engine - echo는 항상 False (로그 노이즈 방지)
if "sqlite" in _database_url:
    engine = create_async_engine(
        _database_url,
        echo=False,
        poolclass=NullPool,
    )
else:
    engine = create_async_engine(
        _database_url,
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


# DB 연결 풀 모니터링 (PostgreSQL/MySQL만, SQLite는 제외)
if "sqlite" not in _database_url and hasattr(engine.sync_engine, "pool"):
    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_conn, connection_record):
        """연결 체크아웃 시 호출."""
        pool = engine.sync_engine.pool
        if hasattr(pool, "size"):
            db_pool_active_connections.set(pool.size())
    
    @event.listens_for(engine.sync_engine, "checkout")
    def _on_checkout(dbapi_conn, connection_record, connection_proxy):
        """연결 체크아웃 시 호출."""
        pool = engine.sync_engine.pool
        if hasattr(pool, "size"):
            db_pool_active_connections.set(pool.size())
        if hasattr(pool, "overflow"):
            db_pool_waiting_requests.set(pool.overflow())
    
    @event.listens_for(engine.sync_engine, "checkin")
    def _on_checkin(dbapi_conn, connection_record):
        """연결 체크인 시 호출."""
        pool = engine.sync_engine.pool
        if hasattr(pool, "size"):
            db_pool_active_connections.set(pool.size())
        if hasattr(pool, "overflow"):
            db_pool_waiting_requests.set(pool.overflow())


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
