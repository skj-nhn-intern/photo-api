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
from app.utils.prometheus_metrics import (
    db_errors_total,
    db_pool_active_connections,
    db_pool_waiting_requests,
)

_logger = logging.getLogger("app.db")

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
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,
    )


# DB 연결 풀 모니터링을 위한 이벤트 리스너
def _update_pool_metrics():
    """연결 풀 메트릭 업데이트."""
    if "sqlite" in _database_url:
        # SQLite는 연결 풀 없음
        db_pool_active_connections.set(0)
        db_pool_waiting_requests.set(0)
        return
    
    try:
        pool = engine.pool
        # 활성 연결 수 (체크아웃된 연결)
        # checkedout()은 현재 사용 중인 연결 수를 반환
        active = pool.checkedout() if hasattr(pool, 'checkedout') else 0
        db_pool_active_connections.set(active)
        
        # 대기 중인 요청 수는 직접 측정 어려움
        # pool.overflow()는 사용 가능한 연결이 없을 때 생성된 추가 연결 수
        # 실제 대기 중인 요청은 pool 내부 상태로만 알 수 있음
        # 간단히 0으로 설정 (향후 개선 가능)
        db_pool_waiting_requests.set(0)
    except Exception as e:
        # 메트릭 업데이트 실패는 무시 (로깅만)
        _logger.debug(f"Failed to update pool metrics: {e}")


@event.listens_for(engine.sync_engine, "checkout")
def _on_checkout(dbapi_conn, connection_record, connection_proxy):
    """연결 체크아웃 시 메트릭 업데이트."""
    _update_pool_metrics()


@event.listens_for(engine.sync_engine, "checkin")
def _on_checkin(dbapi_conn, connection_record):
    """연결 체크인 시 메트릭 업데이트."""
    _update_pool_metrics()


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
