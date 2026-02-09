"""
구조화된 로깅 미들웨어.

모든 HTTP 요청에 대해 자동으로 요청 컨텍스트를 로깅합니다.
"""
import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.logger import (
    set_request_id,
    get_request_id,
    log_with_context,
    log_error,
    log_warning,
)
from app.utils.client_ip import get_client_ip
import logging

logger = logging.getLogger(__name__)

# 느린 응답 임계값 (ms)
SLOW_REQUEST_THRESHOLD_MS = 3000

# Request ID 헤더 이름
REQUEST_ID_HEADER = "X-Request-ID"

# 로깅 제외할 경로
EXCLUDED_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/metrics", "/favicon.ico"}


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    구조화된 로깅을 위한 미들웨어.
    
    기능:
    - Request ID 생성/전파 (장애 추적용)
    - 요청/응답 로깅 (구조화된 포맷)
    - 에러 및 느린 요청 감지
    
    로깅 기준 (운영 노이즈 최소화):
    - 5xx 에러 응답 → ERROR
    - 4xx 에러 응답 → WARNING
    - 느린 응답 (3초 이상) → WARNING
    - 정상 응답 → 로깅 안 함 (필요 시 INFO로 변경 가능)
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        요청 처리 및 로깅.
        
        Args:
            request: FastAPI Request 객체
            call_next: 다음 미들웨어 또는 엔드포인트
            
        Returns:
            Response: 처리된 응답
        """
        # 헬스체크, 문서 등 제외 (Request ID도 불필요)
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)
        
        # Request ID 설정 (클라이언트 제공 또는 새로 생성)
        incoming_rid = request.headers.get(REQUEST_ID_HEADER)
        rid = set_request_id(incoming_rid)
        
        # 클라이언트 정보 추출 (프록시 헤더 고려)
        client_ip = get_client_ip(request)
        user_agent = request.headers.get("user-agent")
        
        start = time.perf_counter()
        
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            
            # 응답 헤더에 Request ID 포함 (클라이언트가 추적 가능)
            response.headers[REQUEST_ID_HEADER] = rid
            
            # 로깅 기준에 따라 로그 레벨 결정
            status_code = response.status_code
            
            # 5xx 서버 에러 → ERROR (즉시 대응 필요)
            if status_code >= 500:
                log_error(
                    "Request error - Server error occurred",
                    error_type="ServerError",
                    error_code=f"HTTP_{status_code}",
                    http_method=request.method,
                    http_path=request.url.path,
                    http_status=status_code,
                    duration_ms=duration_ms,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    request_id=rid,
                    event="request",
                    exc_info=False,
                )
            # 4xx 클라이언트 에러 → WARNING (잠재적 문제)
            elif status_code >= 400:
                log_warning(
                    "Request failed - Client error",
                    http_method=request.method,
                    http_path=request.url.path,
                    http_status=status_code,
                    duration_ms=duration_ms,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    request_id=rid,
                    event="request",
                )
            # 느린 응답 → WARNING (성능 문제 추적)
            elif duration_ms >= SLOW_REQUEST_THRESHOLD_MS:
                log_warning(
                    "Slow request detected",
                    http_method=request.method,
                    http_path=request.url.path,
                    http_status=status_code,
                    duration_ms=duration_ms,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    request_id=rid,
                    event="request",
                    performance_issue=True,
                )
            # 정상 응답은 로깅 안 함 (운영 노이즈 최소화)
            # 필요 시 아래 주석 해제하여 모든 요청 로깅 가능
            # else:
            #     log_info(
            #         "Request completed",
            #         http_method=request.method,
            #         http_path=request.url.path,
            #         http_status=status_code,
            #         duration_ms=duration_ms,
            #         request_id=rid,
            #         event="request",
            #     )
            
            return response
            
        except Exception as e:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            
            # 예외 발생 시 → ERROR
            log_error(
                f"Request exception: {str(e)}",
                error_type=type(e).__name__,
                error_message=str(e),
                http_method=request.method,
                http_path=request.url.path,
                duration_ms=duration_ms,
                client_ip=client_ip,
                user_agent=user_agent,
                request_id=rid,
                event="request",
                exc_info=True,
            )
            
            # 예외를 다시 발생시켜 global exception handler가 처리하도록 함
            raise
