"""
Circuit Breaker 패턴 구현.

외부 서비스 호출 시 장애 전파를 방지하고 빠른 실패(fail-fast)를 제공합니다.
상태 전이: CLOSED → OPEN → HALF_OPEN → CLOSED

참고: https://martinfowler.com/bliki/CircuitBreaker.html
"""
import asyncio
import logging
import time
from enum import Enum
from typing import Callable, TypeVar, Optional

from app.utils.prometheus_metrics import (
    REGISTRY,
    Gauge,
    circuit_breaker_requests_total,
    circuit_breaker_failures_total,
    circuit_breaker_state_transitions_total,
    circuit_breaker_call_duration_seconds,
)

logger = logging.getLogger("app.circuit_breaker")

# Circuit Breaker 상태 메트릭
circuit_breaker_state = Gauge(
    "photo_api_circuit_breaker_state",
    "Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
    ["service"],
    registry=REGISTRY,
)

# 현재 연속 실패 횟수 (OPEN 직전 임계값 근접도·디버깅용)
circuit_breaker_consecutive_failures = Gauge(
    "photo_api_circuit_breaker_consecutive_failures",
    "Current consecutive failure count (resets on success or state transition)",
    ["service"],
    registry=REGISTRY,
)

# 마지막 상태 전이 시각 (Unix timestamp, 초 단위) — OPEN 유지 시간 등 계산용
circuit_breaker_last_state_change_timestamp_seconds = Gauge(
    "photo_api_circuit_breaker_last_state_change_timestamp_seconds",
    "Unix timestamp of last circuit breaker state transition",
    ["service"],
    registry=REGISTRY,
)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit Breaker 상태."""
    CLOSED = "CLOSED"  # 정상 동작, 요청 허용
    OPEN = "OPEN"  # 장애 상태, 요청 차단
    HALF_OPEN = "HALF_OPEN"  # 복구 시도 중, 제한적 요청 허용


class CircuitBreaker:
    """
    Circuit Breaker 구현.
    
    사용 예시:
        breaker = CircuitBreaker("obs_api_server", failure_threshold=5, timeout=60)
        
        async def call_service():
            return await breaker.call(service_function, *args, **kwargs)
    """
    
    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 60.0,
    ):
        """
        Circuit Breaker 초기화.
        
        Args:
            service_name: 서비스 이름 (메트릭 라벨용)
            failure_threshold: OPEN 상태로 전이하기 위한 연속 실패 횟수
            success_threshold: CLOSED 상태로 전이하기 위한 HALF_OPEN에서의 성공 횟수
            timeout: OPEN 상태에서 HALF_OPEN으로 전이하기까지의 시간 (초)
        """
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()
        
        # 초기 상태 메트릭 설정
        circuit_breaker_state.labels(service=service_name).set(0)
        circuit_breaker_consecutive_failures.labels(service=service_name).set(0)
        circuit_breaker_last_state_change_timestamp_seconds.labels(service=service_name).set(
            time.time()
        )
    
    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Circuit Breaker를 통해 함수를 호출.
        
        Args:
            func: 호출할 함수 (async 또는 sync)
            *args, **kwargs: 함수 인자
            
        Returns:
            함수 반환값
            
        Raises:
            CircuitBreakerOpenError: Circuit Breaker가 OPEN 상태일 때
            원본 함수의 예외: 함수 실행 중 발생한 예외
        """
        async with self._lock:
            # 상태 확인 및 전이
            await self._check_and_transition()
            
            # OPEN 상태면 즉시 실패
            if self.state == CircuitState.OPEN:
                circuit_breaker_requests_total.labels(
                    service=self.service_name, status="rejected"
                ).inc()
                logger.warning(
                    f"Circuit breaker OPEN for {self.service_name}, request rejected",
                    extra={"event": "circuit_breaker", "service": self.service_name},
                )
                raise CircuitBreakerOpenError(
                    f"Circuit breaker is OPEN for {self.service_name}"
                )
        
        # HALF_OPEN 또는 CLOSED 상태에서 요청 실행
        start_time = time.perf_counter()
        try:
            # async 함수인지 확인
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # 성공 처리
            async with self._lock:
                await self._on_success()
            
            circuit_breaker_requests_total.labels(
                service=self.service_name, status="success"
            ).inc()
            circuit_breaker_call_duration_seconds.labels(
                service=self.service_name
            ).observe(time.perf_counter() - start_time)
            
            return result
            
        except Exception as e:
            # 실패 처리
            async with self._lock:
                await self._on_failure(e)
            
            circuit_breaker_requests_total.labels(
                service=self.service_name, status="failure"
            ).inc()
            circuit_breaker_call_duration_seconds.labels(
                service=self.service_name
            ).observe(time.perf_counter() - start_time)
            
            raise
    
    async def _check_and_transition(self) -> None:
        """상태 확인 및 자동 전이."""
        if self.state == CircuitState.OPEN:
            # 타임아웃 확인
            if (
                self.last_failure_time
                and time.time() - self.last_failure_time >= self.timeout
            ):
                # HALF_OPEN으로 전이
                circuit_breaker_state_transitions_total.labels(
                    service=self.service_name, from_state=CircuitState.OPEN.value, to_state=CircuitState.HALF_OPEN.value
                ).inc()
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                self.failure_count = 0
                circuit_breaker_state.labels(service=self.service_name).set(2)
                circuit_breaker_consecutive_failures.labels(service=self.service_name).set(0)
                circuit_breaker_last_state_change_timestamp_seconds.labels(service=self.service_name).set(
                    time.time()
                )
                logger.info(
                    f"Circuit breaker transitioning to HALF_OPEN for {self.service_name}",
                    extra={"event": "circuit_breaker", "service": self.service_name},
                )
    
    async def _on_success(self) -> None:
        """성공 처리."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                # CLOSED로 전이
                circuit_breaker_state_transitions_total.labels(
                    service=self.service_name, from_state=CircuitState.HALF_OPEN.value, to_state=CircuitState.CLOSED.value
                ).inc()
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                circuit_breaker_state.labels(service=self.service_name).set(0)
                circuit_breaker_consecutive_failures.labels(service=self.service_name).set(0)
                circuit_breaker_last_state_change_timestamp_seconds.labels(service=self.service_name).set(
                    time.time()
                )
                logger.info(
                    f"Circuit breaker CLOSED for {self.service_name}",
                    extra={"event": "circuit_breaker", "service": self.service_name},
                )
        elif self.state == CircuitState.CLOSED:
            # CLOSED 상태에서는 실패 카운트 리셋
            self.failure_count = 0
            circuit_breaker_consecutive_failures.labels(service=self.service_name).set(0)
    
    async def _on_failure(self, exception: Exception) -> None:
        """실패 처리.
        
        Args:
            exception: 발생한 예외 객체
        """
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        exception_type = type(exception).__name__
        circuit_breaker_failures_total.labels(
            service=self.service_name, exception_type=exception_type
        ).inc()
        
        circuit_breaker_consecutive_failures.labels(service=self.service_name).set(self.failure_count)

        if self.state == CircuitState.HALF_OPEN:
            # HALF_OPEN에서 실패하면 즉시 OPEN으로
            circuit_breaker_state_transitions_total.labels(
                service=self.service_name, from_state=CircuitState.HALF_OPEN.value, to_state=CircuitState.OPEN.value
            ).inc()
            self.state = CircuitState.OPEN
            circuit_breaker_state.labels(service=self.service_name).set(1)
            circuit_breaker_last_state_change_timestamp_seconds.labels(service=self.service_name).set(
                time.time()
            )
            logger.warning(
                f"Circuit breaker OPEN for {self.service_name} (failed in HALF_OPEN)",
                extra={"event": "circuit_breaker", "service": self.service_name},
            )
        elif self.state == CircuitState.CLOSED:
            # CLOSED에서 실패 횟수 확인
            if self.failure_count >= self.failure_threshold:
                circuit_breaker_state_transitions_total.labels(
                    service=self.service_name, from_state=CircuitState.CLOSED.value, to_state=CircuitState.OPEN.value
                ).inc()
                self.state = CircuitState.OPEN
                circuit_breaker_state.labels(service=self.service_name).set(1)
                circuit_breaker_last_state_change_timestamp_seconds.labels(service=self.service_name).set(
                    time.time()
                )
                logger.warning(
                    f"Circuit breaker OPEN for {self.service_name} "
                    f"(failure_count={self.failure_count})",
                    extra={
                        "event": "circuit_breaker",
                        "service": self.service_name,
                        "failure_count": self.failure_count,
                    },
                )


class CircuitBreakerOpenError(Exception):
    """Circuit Breaker가 OPEN 상태일 때 발생하는 예외."""
    pass
