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
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.utils.prometheus_metrics import (
    db_errors_total,
    db_pool_wait_duration_seconds,
    db_pool_timeout_total,
    REGISTRY,
    Gauge,
)
from app.utils.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

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

# DB Circuit Breaker (연결 실패 시 빠른 실패)
# DB 연결이 실패하면 즉시 차단하여 전면 장애 방지
_db_circuit_breaker = CircuitBreaker(
    service_name="database",
    failure_threshold=settings.database_circuit_breaker_failure_threshold,
    success_threshold=2,  # HALF_OPEN에서 2번 성공 시 CLOSED
    timeout=settings.database_circuit_breaker_timeout,
) if settings.database_circuit_breaker_enabled else None

# CI/이미지 검증 시 DATABASE_URL이 비어 있을 수 있음 — 빈 값이면 SQLite 기본 사용
_database_url = (settings.database_url or "").strip()
if not _database_url:
    _database_url = "sqlite+aiosqlite:///./photo_api.db"

# Create async engine - echo는 설정에 따라 (DATABASE_ECHO=true 시 SQL 로그)
_db_echo = settings.database_echo
if "sqlite" in _database_url:
    engine = create_async_engine(
        _database_url,
        echo=_db_echo,
        poolclass=NullPool,
    )
else:
    engine = create_async_engine(
        _database_url,
        echo=_db_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout,
        pool_recycle=settings.database_pool_recycle,
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
# create_async_engine 기본은 AsyncAdaptedQueuePool → sync_engine.pool은 내부 QueuePool 또는 래퍼
if "sqlite" not in _database_url and hasattr(engine, "sync_engine") and hasattr(engine.sync_engine, "pool"):
    def _get_pool():
        p = engine.sync_engine.pool
        # AsyncAdaptedQueuePool 등은 내부 sync QueuePool을 .pool 또는 .sync_pool로 가짐
        return getattr(p, "sync_pool", None) or getattr(p, "pool", p)

    def _pool_metric_total():
        """총 연결 수 = pool_size + overflow (체크아웃 포함). 기존 pool.size()는 대기 중+overflow만 있어 부하 시 0에 가깝게 나옴."""
        pool = _get_pool()
        if not hasattr(pool, "overflow"):
            return
        overflow = pool.overflow()
        pool_size = getattr(pool, "_pool_maxsize", 10)
        total = pool_size + overflow
        db_pool_active_connections.set(total)
        db_pool_waiting_requests.set(overflow)  # overflow 개수(초과 연결 수)

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_conn, connection_record):
        _pool_metric_total()

    @event.listens_for(engine.sync_engine, "checkout")
    def _on_checkout(dbapi_conn, connection_record, connection_proxy):
        _pool_metric_total()

    @event.listens_for(engine.sync_engine, "checkin")
    def _on_checkin(dbapi_conn, connection_record):
        _pool_metric_total()


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
    
    Circuit Breaker를 통해 DB 연결 실패 시 빠른 실패(fail-fast)를 제공하여
    전면 장애를 방지합니다.

    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    # Circuit Breaker를 통해 세션 획득 시도
    async def _get_session():
        wait_start = time.perf_counter()
        try:
            session = await async_session_maker()
            wait_duration = time.perf_counter() - wait_start
            db_pool_wait_duration_seconds.observe(wait_duration)
            return session
        except Exception as e:
            wait_duration = time.perf_counter() - wait_start
            db_pool_wait_duration_seconds.observe(wait_duration)
            
            # 타임아웃 에러인지 확인
            error_str = str(e).lower()
            if "timeout" in error_str or "pool" in error_str:
                db_pool_timeout_total.inc()
            
            raise
    
    # Circuit Breaker가 활성화되어 있으면 사용, 없으면 직접 호출
    if _db_circuit_breaker is not None:
        try:
            session = await _db_circuit_breaker.call(_get_session)
        except CircuitBreakerOpenError:
            # Circuit Breaker가 OPEN 상태 - DB 연결 실패로 인한 전면 장애 방지
            db_errors_total.inc()
            _logger.error(
                "DB circuit breaker OPEN - database connection unavailable",
                extra={"event": "db", "error_type": "CircuitBreakerOpen"},
                exc_info=False,
            )
            raise ConnectionError(
                "Database connection unavailable. Please try again later."
            ) from None
    else:
        # Circuit Breaker 비활성화 시 직접 호출
        session = await _get_session()
    
    try:
        yield session
        await session.commit()
    except Exception as e:
        db_errors_total.inc()
        # DB 관련 간단한 정보만 로깅 (상세 정보는 전역 핸들러에서 처리)
        _logger.error(
            "DB transaction error",
            extra={
                "event": "db",
                "error_type": type(e).__name__,
                "error": str(e)[:200],  # 에러 메시지 앞 200자
            },
            exc_info=False,  # 스택 트레이스는 전역 핸들러에서 처리
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
            # DB 관련 간단한 정보만 로깅 (상세 정보는 전역 핸들러에서 처리)
            _logger.error(
                "DB context error",
                extra={
                    "event": "db",
                    "error_type": type(e).__name__,
                    "error": str(e)[:200],
                },
                exc_info=False,  # 스택 트레이스는 전역 핸들러에서 처리
            )
            await session.rollback()
            raise
        finally:
            await session.close()
