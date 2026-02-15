"""
Request tracking middleware for graceful shutdown.

진행 중인 요청을 추적하여 Graceful shutdown 시 정확한 요청 완료 대기를 보장합니다.
Autoscaling 환경에서 인스턴스 종료 시 안전한 종료를 위해 필수입니다.
"""
import asyncio
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.main import increment_in_flight_requests, decrement_in_flight_requests, get_in_flight_requests
from app.utils.prometheus_metrics import in_flight_requests_metric

logger = logging.getLogger("app.middleware.request_tracking")


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """
    진행 중인 요청을 추적하는 미들웨어.
    
    Graceful shutdown 시:
    1. 요청 시작 시 카운터 증가
    2. 요청 완료 시 카운터 감소
    3. shutdown 시 카운터가 0이 될 때까지 대기
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """요청을 추적하고 처리."""
        # Health check는 제외 (shutdown 시에도 체크 가능해야 함)
        if request.url.path in ["/health", "/health/liveness", "/health/readiness", "/metrics"]:
            return await call_next(request)
        
        # 요청 시작: 카운터 증가
        count = await increment_in_flight_requests()
        in_flight_requests_metric.set(count)
        
        try:
            # 요청 처리
            response = await call_next(request)
            return response
        except Exception as e:
            # 예외 발생 시에도 카운터 감소
            logger.error(
                "Request failed",
                extra={
                    "event": "request_tracking",
                    "path": request.url.path,
                    "method": request.method,
                    "error_type": type(e).__name__,
                }
            )
            raise
        finally:
            # 요청 완료: 카운터 감소
            count = await decrement_in_flight_requests()
            in_flight_requests_metric.set(count)
