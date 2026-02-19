"""
Rate limiting middleware using slowapi.
Provides protection against brute force attacks and DDoS.
"""
import logging
from typing import Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.utils.prometheus_metrics import (
    rate_limit_hits_total,
    rate_limit_requests_total,
)

logger = logging.getLogger("app.rate_limit")
settings = get_settings()

# Rate limiter 인스턴스 생성
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"] if settings.rate_limit_enabled else [],
    storage_uri="memory://",  # 메모리 기반 (분산 환경에서는 Redis 사용 권장)
)


def get_client_identifier(request: Request) -> str:
    """
    클라이언트 식별자 추출 (Rate limiting 키로 사용).
    우선순위: X-Forwarded-For > X-Real-IP > 직접 연결 IP
    """
    # X-Forwarded-For 헤더 확인 (프록시/로드밸런서)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # 여러 IP가 있을 수 있음 (프록시 체인), 첫 번째가 원본 클라이언트
        return forwarded_for.split(",")[0].strip()
    
    # X-Real-IP 헤더 확인
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # 직접 연결 IP
    if request.client:
        return request.client.host
    
    return "unknown"


# Rate limiting 키 함수 업데이트
limiter.key_func = get_client_identifier


def setup_rate_limit_exception_handler(app):
    """
    Rate limit 초과 시 예외 처리 핸들러 등록.
    """
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        """
        Rate limit 초과 시 응답 처리.
        Prometheus 메트릭 수집 및 로깅.
        """
        client_id = get_client_identifier(request)
        endpoint = request.url.path
        
        # Prometheus 메트릭 수집
        rate_limit_hits_total.labels(
            endpoint=endpoint,
            client_id=client_id[:16],  # IP 주소 일부만 (개인정보 보호)
        ).inc()
        
        # Rate limit 체크 요청 수집 (차단됨)
        rate_limit_requests_total.labels(
            endpoint=endpoint,
            status="blocked",
        ).inc()
        
        # 로깅 (WARNING 레벨)
        logger.warning(
            "Rate limit exceeded",
            extra={
                "event": "rate_limit",
                "client_id": client_id,
                "endpoint": endpoint,
                "limit": exc.detail if hasattr(exc, "detail") else "unknown",
            },
        )
        
        # 표준 rate limit 응답
        response = _rate_limit_exceeded_handler(request, exc)
        return response


def get_rate_limit_decorator(limit: str):
    """
    Rate limit 데코레이터 생성 헬퍼.
    
    Args:
        limit: Rate limit 문자열 (예: "10/minute", "60/hour")
    
    Returns:
        Rate limit 데코레이터
    """
    if not settings.rate_limit_enabled:
        # Rate limiting 비활성화 시 빈 데코레이터 반환
        def noop_decorator(func: Callable) -> Callable:
            return func
        return noop_decorator
    
    return limiter.limit(limit)
