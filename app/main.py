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

from fastapi import FastAPI, Request, status, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import traceback

from app.config import get_settings
from app.database import init_db, close_db
from app.routers import auth_router, photos_router, albums_router, share_router
from app.routers import health as health_router
from app.utils.prometheus_metrics import (
    exceptions_total,
    http_5xx_total,
    validation_errors_total,
    ready,
    app_start_time_seconds,
    setup_prometheus,
    pushgateway_loop,
    business_metrics_loop,
    in_flight_requests,
)
from app.middlewares.rate_limit_middleware import setup_rate_limit_exception_handler
from app.middlewares.request_tracking_middleware import RequestTrackingMiddleware
from app.services.nhn_logger import get_logger_service
from app.utils.logger import setup_logging, get_request_id, log_error, log_info, log_warning
from app.utils.client_ip import get_client_ip
from app.utils.config_validator import validate_configuration
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
    # 설정 검증 (프로덕션 환경에서만)
    try:
        await validate_configuration()
    except Exception as e:
        log_error(
            "Configuration validation failed",
            error_type=type(e).__name__,
            error_message=str(e),
            error_code="CONFIG_VALIDATION_ERROR",
            event="lifecycle",
            exc_info=True,
        )
        ready.labels(region=(settings.region or "").strip() or "unknown").set(0)
        raise
    
    log_info(
        "Application startup completed",
        event="lifecycle",
        version=settings.app_version,
        environment=settings.environment.value,
    )
    await init_db()
    ready.labels(region=(settings.region or "").strip() or "unknown").set(1)  # Health check 통과: 설정 검증·DB 초기화 완료 후
    app_start_time_seconds.set(int(time.time()))  # FastAPI 상태 모니터링: 업타임 계산용
    logger_service = get_logger_service()
    await logger_service.start()

    # Pushgateway 연동: PROMETHEUS_PUSHGATEWAY_URL 설정 시 백그라운드에서 주기 푸시
    pushgateway_task = asyncio.create_task(pushgateway_loop())
    # 비즈니스 메트릭 + Temp URL 업로드 추적: 60초마다 DB 집계 후 Gauge 갱신
    business_metrics_task = asyncio.create_task(business_metrics_loop())

    yield

    # Shutdown
    ready.labels(region=(settings.region or "").strip() or "unknown").set(0)  # Health check 즉시 실패
    log_info("Application shutdown initiated", event="lifecycle")
    
    # 진행 중인 요청 완료 대기 (최대 30초)
    # 실제 운영 환경에서는 로드밸런서가 새 요청을 차단하므로
    # 진행 중인 요청만 완료하면 됨
    shutdown_timeout = 30.0
    shutdown_start = time.time()
    
    # 진행 중인 요청이 있는지 확인 (메트릭으로 확인)
    while time.time() - shutdown_start < shutdown_timeout:
        current_count = in_flight_requests._value.get()
        if current_count == 0:
            log_info(
                "All in-flight requests completed",
                event="lifecycle",
            )
            break
        await asyncio.sleep(0.5)
    else:
        remaining = in_flight_requests._value.get()
        if remaining > 0:
            log_warning(
                f"Shutdown timeout: {remaining} requests still in flight",
                event="lifecycle",
                remaining_requests=remaining,
            )
    
    pushgateway_task.cancel()
    business_metrics_task.cancel()
    try:
        await pushgateway_task
    except asyncio.CancelledError:
        pass
    try:
        await business_metrics_task
    except asyncio.CancelledError:
        pass

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
# 진행 중인 요청 추적: Graceful shutdown용
app.add_middleware(RequestTrackingMiddleware)


# ValueError를 HTTPException으로 변환
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """
    ValueError를 400 Bad Request로 변환.
    비즈니스 로직 검증 실패 시 사용.
    """
    rid = get_request_id()
    client_ip = get_client_ip(request)
    
    log_warning(
        "ValueError occurred",
        error_type=type(exc).__name__,
        error_message=str(exc),
        error_code="VALIDATION_ERROR",
        http_method=request.method,
        http_path=request.url.path,
        request_id=rid,
        client_ip=client_ip,
        event="exception",
    )
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": str(exc),
            "request_id": rid,
        },
    )


# 요청 바디/파라미터 검증 실패 (422) — 클라이언트 입력 문제, 서버 안정성과 구분
@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    """RequestValidationError → 422, validation_errors_total 증가."""
    validation_errors_total.inc()
    rid = get_request_id()
    log_warning(
        "Request validation failed",
        error_type=type(exc).__name__,
        error_message=str(exc.errors()),
        http_method=request.method,
        http_path=request.url.path,
        request_id=rid,
        event="validation",
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "request_id": rid,
        },
    )


# Global exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    HTTPException 핸들러 - 이미 적절한 HTTP 응답이므로 그대로 반환.
    4xx 에러는 WARNING, 5xx 에러는 ERROR로 로깅.
    """
    rid = get_request_id()
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent")
    
    # 4xx는 클라이언트 오류 (WARNING), 5xx는 서버 오류 (ERROR)
    if exc.status_code >= 500:
        exceptions_total.labels(exception_type="HTTPException_5xx").inc()
        http_5xx_total.inc()
        log_error(
            "HTTP exception occurred",
            error_type=type(exc).__name__,
            error_message=str(exc.detail),
            error_code=f"HTTP_{exc.status_code}",
            http_method=request.method,
            http_path=request.url.path,
            http_status=exc.status_code,
            request_id=rid,
            client_ip=client_ip,
            user_agent=user_agent,
            query_params=dict(request.query_params) if request.query_params else None,
            event="exception",
            exc_info=False,
        )
    elif exc.status_code >= 400:
        log_warning(
            "Client error",
            error_type=type(exc).__name__,
            error_message=str(exc.detail),
            error_code=f"HTTP_{exc.status_code}",
            http_method=request.method,
            http_path=request.url.path,
            http_status=exc.status_code,
            request_id=rid,
            client_ip=client_ip,
            user_agent=user_agent,
            event="exception",
        )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "request_id": rid,
        },
        headers=exc.headers,
    )


def _make_500_response(request: Request, exc: Exception) -> JSONResponse:
    """전역 예외 시 500 응답 및 로깅 공통 처리 (RuntimeError 재사용용)."""
    exc_type = type(exc).__name__
    exceptions_total.labels(exception_type=exc_type).inc()
    http_5xx_total.inc()
    rid = get_request_id()
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent")
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    stack_trace = "".join(tb_lines)
    request_body = None
    try:
        if hasattr(request, "_body"):
            body = request._body
            if body and len(body) < 1000:
                request_body = body.decode("utf-8", errors="ignore")[:500]
    except Exception:
        pass
    log_error(
        "Unhandled exception occurred",
        error_type=exc_type,
        error_message=str(exc),
        error_code="INTERNAL_SERVER_ERROR",
        http_method=request.method,
        http_path=request.url.path,
        http_status=500,
        request_id=rid,
        client_ip=client_ip,
        user_agent=user_agent,
        query_params=dict(request.query_params) if request.query_params else None,
        request_body_preview=request_body,
        stack_trace=stack_trace,
        event="exception",
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "request_id": rid},
    )


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError):
    """
    RuntimeError 중 'No response returned.'는 클라이언트가 응답 전에 연결을 끊은 경우.
    Starlette BaseHTTPMiddleware에서 발생하므로 499로 처리해 5xx와 구분한다.
    """
    if exc.args and exc.args[0] == "No response returned.":
        rid = get_request_id()
        log_warning(
            "Client closed connection before response was sent",
            error_type=type(exc).__name__,
            error_message=str(exc),
            error_code="CLIENT_CLOSED_REQUEST",
            http_method=request.method,
            http_path=request.url.path,
            http_status=499,
            request_id=rid,
            client_ip=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            event="exception",
        )
        return JSONResponse(
            status_code=499,
            content={"detail": "Client closed request.", "request_id": rid},
        )
    return _make_500_response(request, exc)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    전역 예외 핸들러 - 트러블슈팅을 위한 풍부한 정보 수집.
    
    모든 처리되지 않은 예외를 캐치하여:
    - 상세한 ERROR 로그 (스택 트레이스, 요청 컨텍스트 포함)
    - 500 응답 반환
    - Request ID 포함 (장애 추적용)
    """
    return _make_500_response(request, exc)


# Include routers
app.include_router(auth_router)
app.include_router(photos_router)
app.include_router(albums_router)
app.include_router(share_router)
app.include_router(health_router.router)


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


# Health check는 health_router로 이동됨


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
