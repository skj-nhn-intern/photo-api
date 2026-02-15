"""
Circuit Breaker pattern implementation for external service calls.

Circuit Breaker는 외부 서비스 장애 시 빠른 실패(fail-fast)를 통해
리소스 낭비를 방지하고 장애 전파를 막습니다.

상태 전이:
- CLOSED → OPEN: 실패율이 threshold 초과
- OPEN → HALF_OPEN: timeout 후 (테스트 모드)
- HALF_OPEN → CLOSED: 성공
- HALF_OPEN → OPEN: 실패
"""
import asyncio
import logging
import time
from enum import Enum
from typing import Callable, TypeVar, Optional

from app.utils.prometheus_metrics import circuit_breaker_state

logger = logging.getLogger("app.circuit_breaker")

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker 상태."""
    CLOSED = "closed"  # 정상 동작
    OPEN = "open"      # 차단 (실패율 높음)
    HALF_OPEN = "half_open"  # 테스트 중


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.
    
    외부 서비스 장애 시:
    1. 실패가 누적되면 OPEN 상태로 전이 (요청 차단)
    2. 일정 시간 후 HALF_OPEN으로 전이 (테스트)
    3. 테스트 성공 시 CLOSED로 복구
    
    Args:
        failure_threshold: OPEN 전이를 위한 실패 횟수 (default: 5)
        success_threshold: HALF_OPEN → CLOSED 전이를 위한 성공 횟수 (default: 2)
        timeout: OPEN → HALF_OPEN 전이 대기 시간 (초, default: 60.0)
        expected_exception: 재시도할 예외 타입 (default: Exception)
        service_name: 서비스 이름 (메트릭용)
    
    Example:
        ```python
        storage_breaker = CircuitBreaker(
            failure_threshold=5,
            timeout=60.0,
            service_name="nhn_storage"
        )
        
        try:
            result = await storage_breaker.call(
                storage_service.upload_file,
                file_content=data,
                object_name="path/to/file.jpg"
            )
        except Exception as e:
            # Circuit breaker가 OPEN이거나 함수 실행 실패
            logger.error(f"Upload failed: {e}")
        ```
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 60.0,
        expected_exception: tuple = (Exception,),
        service_name: str = "unknown",
    ):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        self.service_name = service_name
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()
        
        # Prometheus 메트릭 초기화
        circuit_breaker_state.labels(service=service_name, state="closed").set(1)
    
    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Async function to execute
            *args, **kwargs: Arguments to pass to func
        
        Returns:
            Result of func
        
        Raises:
            Exception: Circuit breaker is OPEN or function execution failed
        """
        async with self._lock:
            # 상태 확인
            if self.state == CircuitState.OPEN:
                if self.last_failure_time and time.time() - self.last_failure_time >= self.timeout:
                    # Timeout 지나면 HALF_OPEN으로 전이
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    self.failure_count = 0
                    self._update_metrics("half_open")
                    logger.info(
                        f"Circuit breaker [{self.service_name}]: OPEN → HALF_OPEN",
                        extra={"event": "circuit_breaker", "service": self.service_name}
                    )
                else:
                    # 아직 차단 상태
                    raise Exception(f"Circuit breaker [{self.service_name}] is OPEN")
        
        try:
            # 함수 실행
            result = await func(*args, **kwargs)
            
            # 성공 처리
            async with self._lock:
                if self.state == CircuitState.HALF_OPEN:
                    self.success_count += 1
                    if self.success_count >= self.success_threshold:
                        self.state = CircuitState.CLOSED
                        self.failure_count = 0
                        self._update_metrics("closed")
                        logger.info(
                            f"Circuit breaker [{self.service_name}]: HALF_OPEN → CLOSED",
                            extra={"event": "circuit_breaker", "service": self.service_name}
                        )
                elif self.state == CircuitState.CLOSED:
                    self.failure_count = 0  # 성공 시 카운터 리셋
            
            return result
            
        except self.expected_exception as e:
            # 실패 처리
            async with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.state == CircuitState.HALF_OPEN:
                    # HALF_OPEN에서 실패 → OPEN
                    self.state = CircuitState.OPEN
                    self._update_metrics("open")
                    logger.warning(
                        f"Circuit breaker [{self.service_name}]: HALF_OPEN → OPEN",
                        extra={
                            "event": "circuit_breaker",
                            "service": self.service_name,
                            "error_type": type(e).__name__,
                        }
                    )
                elif self.state == CircuitState.CLOSED:
                    if self.failure_count >= self.failure_threshold:
                        # CLOSED에서 실패율 초과 → OPEN
                        self.state = CircuitState.OPEN
                        self._update_metrics("open")
                        logger.warning(
                            f"Circuit breaker [{self.service_name}]: CLOSED → OPEN (failures: {self.failure_count})",
                            extra={
                                "event": "circuit_breaker",
                                "service": self.service_name,
                                "failure_count": self.failure_count,
                            }
                        )
            
            raise
    
    def _update_metrics(self, state: str):
        """Update Prometheus metrics for circuit breaker state."""
        # 모든 상태를 0으로 리셋
        circuit_breaker_state.labels(service=self.service_name, state="closed").set(0)
        circuit_breaker_state.labels(service=self.service_name, state="open").set(0)
        circuit_breaker_state.labels(service=self.service_name, state="half_open").set(0)
        
        # 현재 상태를 1로 설정
        circuit_breaker_state.labels(service=self.service_name, state=state).set(1)
    
    def get_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        return self.state
    
    def reset(self):
        """Reset circuit breaker to CLOSED state (for testing)."""
        async def _reset():
            async with self._lock:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.last_failure_time = None
                self._update_metrics("closed")
        
        # 비동기 함수이므로 실행 필요
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_reset())
        else:
            loop.run_until_complete(_reset())


# 서비스별 Circuit Breaker 인스턴스
_storage_breaker: Optional[CircuitBreaker] = None
_cdn_breaker: Optional[CircuitBreaker] = None


def get_storage_circuit_breaker() -> CircuitBreaker:
    """Get circuit breaker for Object Storage service."""
    global _storage_breaker
    if _storage_breaker is None:
        _storage_breaker = CircuitBreaker(
            failure_threshold=5,
            success_threshold=2,
            timeout=60.0,
            service_name="nhn_storage",
        )
    return _storage_breaker


def get_cdn_circuit_breaker() -> CircuitBreaker:
    """Get circuit breaker for CDN service."""
    global _cdn_breaker
    if _cdn_breaker is None:
        _cdn_breaker = CircuitBreaker(
            failure_threshold=5,
            success_threshold=2,
            timeout=60.0,
            service_name="nhn_cdn",
        )
    return _cdn_breaker
