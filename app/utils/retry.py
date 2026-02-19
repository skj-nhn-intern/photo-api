"""
재시도 로직 구현 (Exponential Backoff).

외부 서비스 호출 실패 시 자동 재시도를 제공합니다.
지수 백오프를 사용하여 서비스 부하를 완화합니다.
"""
import asyncio
import logging
import random
from typing import Callable, TypeVar, Optional, Type

logger = logging.getLogger("app.retry")

T = TypeVar("T")


async def retry_with_backoff(
    func: Callable[..., T],
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
    target: Optional[str] = None,
    *args,
    **kwargs,
) -> T:
    """
    Exponential Backoff를 사용한 재시도 로직.
    
    Args:
        func: 호출할 함수 (async 또는 sync)
        max_attempts: 최대 재시도 횟수 (총 시도 횟수 = max_attempts)
        initial_delay: 초기 지연 시간 (초)
        max_delay: 최대 지연 시간 (초)
        exponential_base: 지수 백오프 베이스
        jitter: 지터(랜덤 지연) 추가 여부
        retryable_exceptions: 재시도할 예외 타입
        target: 재시도 대상 식별 (예: "storage.upload", "cdn.token") — 로그/대시보드용
        *args, **kwargs: 함수 인자
        
    Returns:
        함수 반환값
        
    Raises:
        마지막 시도에서 발생한 예외
    """
    last_exception: Optional[Exception] = None
    
    for attempt in range(max_attempts):
        try:
            # async 함수인지 확인
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
                
        except retryable_exceptions as e:
            last_exception = e
            
            # 마지막 시도면 예외 발생
            if attempt == max_attempts - 1:
                extra_err = {
                    "event": "retry",
                    "attempt": attempt + 1,
                    "max_attempts": max_attempts,
                    "error_type": type(e).__name__,
                }
                if target is not None:
                    extra_err["retry_target"] = target
                logger.error(
                    f"Retry exhausted after {max_attempts} attempts",
                    extra=extra_err,
                    exc_info=True,
                )
                raise
            
            # 지연 시간 계산 (지수 백오프)
            delay = min(
                initial_delay * (exponential_base ** attempt),
                max_delay,
            )
            
            # 지터 추가 (선택적)
            if jitter:
                delay = delay * (0.5 + random.random() * 0.5)  # 50% ~ 150%
            
            extra_warn = {
                "event": "retry",
                "attempt": attempt + 1,
                "max_attempts": max_attempts,
                "delay": delay,
                "error_type": type(e).__name__,
            }
            if target is not None:
                extra_warn["retry_target"] = target
            logger.warning(
                f"Retry attempt {attempt + 1}/{max_attempts} after {delay:.2f}s",
                extra=extra_warn,
            )
            
            await asyncio.sleep(delay)
    
    # 이 코드는 도달하지 않아야 하지만 타입 체커를 위해
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic error")


def retry_sync(
    func: Callable[..., T],
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
    target: Optional[str] = None,
    *args,
    **kwargs,
) -> T:
    """
    동기 함수용 재시도 로직 (간단한 버전).
    
    Args:
        func: 호출할 동기 함수
        max_attempts: 최대 재시도 횟수
        initial_delay: 초기 지연 시간 (초)
        max_delay: 최대 지연 시간 (초)
        exponential_base: 지수 백오프 베이스
        retryable_exceptions: 재시도할 예외 타입
        target: 재시도 대상 식별 (예: "storage.upload", "cdn.token") — 로그/대시보드용
        *args, **kwargs: 함수 인자
        
    Returns:
        함수 반환값
    """
    import time
    
    last_exception: Optional[Exception] = None
    
    for attempt in range(max_attempts):
        try:
            return func(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e
            
            if attempt == max_attempts - 1:
                extra_err = {
                    "event": "retry",
                    "attempt": attempt + 1,
                    "max_attempts": max_attempts,
                    "error_type": type(e).__name__,
                }
                if target is not None:
                    extra_err["retry_target"] = target
                logger.error(
                    f"Sync retry exhausted after {max_attempts} attempts",
                    extra=extra_err,
                )
                raise
            
            delay = min(
                initial_delay * (exponential_base ** attempt),
                max_delay,
            )
            
            extra_warn = {
                "event": "retry",
                "attempt": attempt + 1,
                "max_attempts": max_attempts,
                "delay": delay,
                "error_type": type(e).__name__,
            }
            if target is not None:
                extra_warn["retry_target"] = target
            logger.warning(
                f"Sync retry attempt {attempt + 1}/{max_attempts} after {delay:.2f}s",
                extra=extra_warn,
            )
            
            time.sleep(delay)
    
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic error")
