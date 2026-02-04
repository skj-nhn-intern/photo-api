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
from app.utils.logger import setup_logging

settings = get_settings()
logger = logging.getLogger("app")

# Python logging 설정
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan: startup / shutdown."""
    ready.set(1)
    logger.info("Startup", extra={"event": "lifecycle", "version": settings.app_version})
    await init_db()
    logger_service = get_logger_service()
    await logger_service.start()

    yield

    ready.set(0)
    logger.info("Shutdown", extra={"event": "lifecycle"})
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
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        extra={
            "event": "exception",
            "path": request.url.path,
            "method": request.method,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# 느린 응답 임계값 (ms)
SLOW_REQUEST_THRESHOLD_MS = 3000


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    요청 로깅 미들웨어.
    
    로깅 기준 (운영 노이즈 최소화):
    - 4xx/5xx 에러 응답 → WARNING/ERROR
    - 느린 응답 (3초 이상) → WARNING
    - 정상 응답 → 로깅 안 함
    """
    # 헬스체크, 문서 등 제외
    if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc", "/metrics"):
        return await call_next(request)
    
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000)
    
    log_data = {
        "event": "request",
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "ms": duration_ms,
    }
    
    # 5xx 서버 에러 → ERROR
    if response.status_code >= 500:
        logger.error("Request error", extra=log_data)
    # 4xx 클라이언트 에러 → WARNING
    elif response.status_code >= 400:
        logger.warning("Request failed", extra=log_data)
    # 느린 응답 → WARNING
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
