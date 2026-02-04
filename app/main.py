"""
FastAPI Photo API Application.

Main application entry point that configures:
- CORS middleware
- API routers
- Database lifecycle
- Logging system
- Exception handlers
"""
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
from app.utils.prometheus_metrics import exceptions_total, ready, setup_prometheus
from app.services.nhn_logger import get_logger_service
from app.utils.logger import setup_logging, set_request_id, get_request_id, INSTANCE_IP

settings = get_settings()
logger = logging.getLogger("app")

# Python logging 설정
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan: startup / shutdown."""
    ready.set(1)
    logger.info(
        "Startup",
        extra={
            "event": "lifecycle",
            "version": settings.app_version,
            "instance": INSTANCE_IP,
            "environment": settings.environment.value,
        },
    )
    await init_db()
    logger_service = get_logger_service()
    await logger_service.start()

    yield

    ready.set(0)
    logger.info("Shutdown", extra={"event": "lifecycle", "instance": INSTANCE_IP})
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

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Unhandled exception → ERROR 로그 + 500 응답."""
    exceptions_total.inc()
    rid = get_request_id()
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        extra={
            "event": "exception",
            "path": request.url.path,
            "method": request.method,
            "rid": rid,
        },
    )
    # 클라이언트에게 Request ID 반환 (장애 추적용)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "request_id": rid,  # 사용자가 이 ID로 문의 가능
        },
    )


# 느린 응답 임계값 (ms)
SLOW_REQUEST_THRESHOLD_MS = 3000

# Request ID 헤더 이름
REQUEST_ID_HEADER = "X-Request-ID"


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    요청 로깅 미들웨어.
    
    기능:
    - Request ID 생성/전파 (장애 추적용)
    - 요청/응답 로깅
    
    로깅 기준 (운영 노이즈 최소화):
    - 4xx/5xx 에러 응답 → WARNING/ERROR
    - 느린 응답 (3초 이상) → WARNING
    - 정상 응답 → 로깅 안 함
    """
    # 헬스체크, 문서 등 제외 (Request ID도 불필요)
    if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc", "/metrics"):
        return await call_next(request)
    
    # Request ID 설정 (클라이언트 제공 또는 새로 생성)
    incoming_rid = request.headers.get(REQUEST_ID_HEADER)
    rid = set_request_id(incoming_rid)
    
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000)
    
    # 응답 헤더에 Request ID 포함 (클라이언트가 추적 가능)
    response.headers[REQUEST_ID_HEADER] = rid
    
    log_data = {
        "event": "request",
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "ms": duration_ms,
        # rid는 JsonLinesFormatter에서 자동 추가되지만, 명시적으로도 포함
    }
    
    # 5xx 서버 에러 → ERROR (상세 정보 포함)
    if response.status_code >= 500:
        log_data["client_ip"] = request.client.host if request.client else None
        logger.error("Request error", extra=log_data)
    # 4xx 클라이언트 에러 → WARNING
    elif response.status_code >= 400:
        logger.warning("Request failed", extra=log_data)
    # 느린 응답 → WARNING (성능 문제 추적)
    elif duration_ms >= SLOW_REQUEST_THRESHOLD_MS:
        logger.warning("Slow request", extra=log_data)
    # 정상 응답은 로깅 안 함 (운영 노이즈 최소화)
    
    return response


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
