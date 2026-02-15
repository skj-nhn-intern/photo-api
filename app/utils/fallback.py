"""
Fallback strategies for external service failures.

외부 서비스 장애 시 Fallback 전략을 제공합니다.
현재는 예시 구현만 제공하며, 실제 사용 시 비즈니스 요구사항에 맞게 수정해야 합니다.
"""
import logging
from typing import Optional
from enum import Enum

logger = logging.getLogger("app.fallback")


class ServiceStatus(Enum):
    """외부 서비스 상태."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # 부분적 장애 (읽기만 가능)
    DOWN = "down"  # 완전 장애


class FallbackStrategy:
    """
    Fallback 전략 관리자.
    
    현재는 예시 구현만 제공합니다.
    실제 운영 환경에서는 비즈니스 요구사항에 맞게 구현해야 합니다.
    """
    
    def __init__(self):
        self._storage_status = ServiceStatus.HEALTHY
        self._cdn_status = ServiceStatus.HEALTHY
    
    def get_storage_status(self) -> ServiceStatus:
        """Object Storage 상태 반환."""
        return self._storage_status
    
    def set_storage_status(self, status: ServiceStatus):
        """Object Storage 상태 설정."""
        self._storage_status = status
        logger.info(
            f"Storage status changed to {status.value}",
            extra={"event": "fallback", "service": "storage", "status": status.value}
        )
    
    def is_storage_read_only(self) -> bool:
        """Object Storage가 읽기 전용 모드인지 확인."""
        return self._storage_status == ServiceStatus.DEGRADED
    
    def is_storage_available(self) -> bool:
        """Object Storage가 사용 가능한지 확인."""
        return self._storage_status != ServiceStatus.DOWN
    
    def get_cdn_status(self) -> ServiceStatus:
        """CDN 상태 반환."""
        return self._cdn_status
    
    def set_cdn_status(self, status: ServiceStatus):
        """CDN 상태 설정."""
        self._cdn_status = status
        logger.info(
            f"CDN status changed to {status.value}",
            extra={"event": "fallback", "service": "cdn", "status": status.value}
        )


# Singleton instance
_fallback_strategy: Optional[FallbackStrategy] = None


def get_fallback_strategy() -> FallbackStrategy:
    """Get the singleton fallback strategy instance."""
    global _fallback_strategy
    if _fallback_strategy is None:
        _fallback_strategy = FallbackStrategy()
    return _fallback_strategy
