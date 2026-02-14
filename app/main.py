"""
FastAPI Photo API Application.

Main application entry point that configures:
- CORS middleware
- API routers
- Database lifecycle
- Logging system
- Exception handlers
- Prometheus metrics (스크래핑 + 선택적 Pushgateway)
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import init_db, close_db
from app.routers import auth_router, photos_router, albums_router, share_router
from app.utils.prometheus_metrics import (
    exceptions_total,
    ready,
    setup_prometheus,
    pushgateway_loop,
)
from app.middlewares.rate_limit_middleware import setup_rate_limit_exception_handler
from app.services.nhn_logger import get_logger_service
from app.utils.logger import setup_logging, get_request_id, log_error, log_info
from app.middlewares.logging_middleware import LoggingMiddleware
from app.middlewares.active_sessions_middleware import ActiveSessionsMiddleware
from app.utils.client_ip import get_client_ip, get_forwarded_proto, get_forwarded_host

settings = get_settings()
logger = logging.getLogger("app")

# Python logging 설정
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan: startup / shutdown."""
    ready.set(1)
    log_info(
        "Application startup completed",
        event="lifecycle",
        version=settings.app_version,
        environment=settings.environment.value,
    )
    await init_db()
    logger_service = get_logger_service()
    await logger_service.start()

    # Pushgateway 연동: PROMETHEUS_PUSHGATEWAY_URL 설정 시 백그라운드에서 주기 푸시
    pushgateway_task = asyncio.create_task(pushgateway_loop())

    yield

    pushgateway_task.cancel()
    try:
        await pushgateway_task
    except asyncio.CancelledError:
        pass

    ready.set(0)
    log_info("Application shutdown initiated", event="lifecycle")
    await logger_service.stop()
    await close_db()


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
## Photo API

A photo management API built with FastAPI, featuring:

### Features
- **User Management**: Registration and JWT authentication
- **Photo Management**: Upload, view, and delete photos
- **Album Management**: Create albums and organize photos
- **Sharing**: Generate public share links for albums

### NHN Cloud Integration
- **Object Storage**: Photo file storage
- **CDN with Auth Token**: Secure photo delivery
- **Log & Crash**: Centralized logging

### Authentication
Most endpoints require authentication via Bearer token.
Use the `/auth/login` endpoint to get a token.
    """,
    openapi_tags=[
        {"name": "Authentication", "description": "User registration and login"},
        {"name": "Photos", "description": "Photo upload and management"},
        {"name": "Albums", "description": "Album management and photo organization"},
        {"name": "Shared Albums", "description": "Public access to shared albums"},
    ],
    lifespan=lifespan,
)

# Prometheus: FastAPI metrics + node info at /metrics
setup_prometheus(app)

# Rate limiting: 예외 처리 핸들러 등록
setup_rate_limit_exception_handler(app)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add structured logging middleware
app.add_middleware(LoggingMiddleware)
# 활성 세션 수: 인증된 요청 종료 시 Gauge 감소
app.add_middleware(ActiveSessionsMiddleware)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Unhandled exception handler with structured logging.
    
    모든 처리되지 않은 예외를 캐치하여:
    - ERROR 로그 남김 (구조화된 포맷)
    - 500 응답 반환
    - Request ID 포함 (장애 추적용)
    """
    exceptions_total.inc()
    rid = get_request_id()
    
    log_error(
        "Unhandled exception occurred",
        error_type=type(exc).__name__,
        error_message=str(exc),
        error_code="INTERNAL_SERVER_ERROR",
        http_method=request.method,
        http_path=request.url.path,
        request_id=rid,
        event="exception",
        exc_info=True,
    )
    
    # 클라이언트에게 Request ID 반환 (장애 추적용)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "request_id": rid,  # 사용자가 이 ID로 문의 가능
        },
    )


# Include routers
app.include_router(auth_router)
app.include_router(photos_router)
app.include_router(albums_router)
app.include_router(share_router)


# Root endpoint
@app.get(
    "/",
    tags=["Root"],
    summary="API information",
)
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }


# Health check endpoint
@app.get(
    "/health",
    tags=["Health"],
    summary="Health check",
)
async def health_check():
    """
    Health check endpoint for load balancer.
    Returns 200 OK if the service is running.
    """
    return {"status": "healthy"}


# Debug endpoint for client IP
@app.get(
    "/debug/client-info",
    tags=["Debug"],
    summary="Debug: Client IP and headers",
)
async def debug_client_info(request: Request):
    """
    디버깅용: 클라이언트 IP 및 헤더 정보 조회.
    
    프록시/로드밸런서 설정이 올바른지 확인하는 데 사용합니다.
    
    **주의:** 프로덕션 환경에서는 제거하거나 인증을 추가하는 것을 권장합니다.
    
    Returns:
        - client_ip: 추출된 실제 클라이언트 IP
        - request_client_host: FastAPI가 보는 직접 연결 IP
        - headers: 프록시 관련 헤더들
        - url: 요청 URL 정보
    """
    return {
        "client_ip": get_client_ip(request),
        "request_client_host": request.client.host if request.client else None,
        "forwarded_proto": get_forwarded_proto(request),
        "forwarded_host": get_forwarded_host(request),
        "headers": {
            "x-forwarded-for": request.headers.get("X-Forwarded-For"),
            "x-real-ip": request.headers.get("X-Real-IP"),
            "x-forwarded-proto": request.headers.get("X-Forwarded-Proto"),
            "x-forwarded-host": request.headers.get("X-Forwarded-Host"),
            "user-agent": request.headers.get("User-Agent"),
            "cf-connecting-ip": request.headers.get("CF-Connecting-IP"),
            "true-client-ip": request.headers.get("True-Client-IP"),
            "host": request.headers.get("Host"),
        },
        "url": {
            "scheme": request.url.scheme,
            "host": request.url.hostname,
            "port": request.url.port,
            "path": request.url.path,
            "full_url": str(request.url),
        },
        "note": "이 엔드포인트는 프로덕션에서 제거하거나 인증을 추가하세요.",
    }
