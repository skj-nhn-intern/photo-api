"""
진행 중인 요청 추적 미들웨어.

Graceful shutdown 시 진행 중인 요청을 추적하여 안전하게 종료할 수 있게 합니다.
"""
import asyncio
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.prometheus_metrics import in_flight_requests

logger = logging.getLogger("app.request_tracking")

# Health check 경로는 제외 (shutdown 시에도 체크 가능해야 함)
EXCLUDED_PATHS = {"/health", "/health/liveness", "/health/readiness", "/health/detailed"}


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """
    진행 중인 요청을 추적하는 미들웨어.
    
    Graceful shutdown 시 진행 중인 요청을 완료할 때까지 대기할 수 있게 합니다.
    """
    
    def __init__(self, app):
        super().__init__(app)
        self._lock = asyncio.Lock()
        self._request_count = 0
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        요청 처리 및 추적.
        
        Args:
            request: FastAPI Request 객체
            call_next: 다음 미들웨어 또는 엔드포인트
            
        Returns:
            Response: 처리된 응답
        """
        # Health check는 제외 (shutdown 시에도 체크 가능해야 함)
        if request.url.path in EXCLUDED_PATHS:
            return await call_next(request)
        
        # 요청 시작: 카운터 증가
        async with self._lock:
            self._request_count += 1
            in_flight_requests.set(self._request_count)
        
        try:
            # 요청 처리
            response = await call_next(request)
            return response
        finally:
            # 요청 완료: 카운터 감소
            async with self._lock:
                self._request_count -= 1
                if self._request_count < 0:
                    self._request_count = 0  # 안전장치
                in_flight_requests.set(self._request_count)
    
    async def wait_for_requests(self, timeout: float = 30.0) -> bool:
        """
        진행 중인 요청이 완료될 때까지 대기.
        
        Args:
            timeout: 최대 대기 시간 (초)
            
        Returns:
            True: 모든 요청 완료, False: 타임아웃
        """
        import time
        
        start_time = time.time()
        
        while True:
            async with self._lock:
                count = self._request_count
            
            if count == 0:
                logger.info(
                    "All in-flight requests completed",
                    extra={"event": "shutdown"},
                )
                return True
            
            if time.time() - start_time >= timeout:
                logger.warning(
                    f"Timeout waiting for requests (remaining: {count})",
                    extra={
                        "event": "shutdown",
                        "remaining_requests": count,
                        "timeout": timeout,
                    },
                )
                return False
            
            # 짧은 간격으로 재확인
            await asyncio.sleep(0.5)
