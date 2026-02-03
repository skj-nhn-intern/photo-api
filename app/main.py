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
from app.services.nhn_logger import (
    get_logger_service,
    log_info,
    log_error,
    log_exception,
)
from app.utils.logger import setup_logging

settings = get_settings()

# Python logging 설정 (파일 및 journald용)
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan: startup / shutdown 한 번씩만 로그."""
    ready.set(1)
    log_info("Startup", event="lifecycle", version=settings.app_version)
    await init_db()
    logger_service = get_logger_service()
    await logger_service.start()

    yield

    ready.set(0)
    log_info("Shutdown", event="lifecycle")
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
    """
    Global exception handler for unhandled exceptions.
    Logs the error and returns a generic error response.
    """
    exceptions_total.inc()
    log_exception(
        "Unhandled exception",
        exc,
        event="exception",
        path=request.url.path,
        method=request.method,
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# 요청당 한 줄 로그 (method, path, status_code, duration_ms). /health 제외.
@app.middleware("http")
async def log_requests(request: Request, call_next):
    if request.url.path in ["/docs", "/openapi.json", "/redoc", "/health"]:
        return await call_next(request)
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000)
    log_info(
        "Request",
        event="request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
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
