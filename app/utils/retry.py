"""
Retry utility with exponential backoff for external service calls.
"""
import asyncio
import logging
from typing import Callable, TypeVar, Optional, Tuple, Any

logger = logging.getLogger("app.retry")

T = TypeVar('T')

# 기본 재시도 가능한 예외 (네트워크/일시적 오류)
DEFAULT_RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
)


async def retry_with_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    retryable_exceptions: Tuple[type, ...] = DEFAULT_RETRYABLE_EXCEPTIONS,
    *args,
    **kwargs
) -> T:
    """
    Retry a function with exponential backoff.
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 10.0)
        exponential_base: Base for exponential backoff (default: 2.0)
        retryable_exceptions: Tuple of exceptions to retry
        *args, **kwargs: Arguments to pass to func
    
    Returns:
        Result of func
    
    Raises:
        Last exception if all retries fail
    
    Example:
        ```python
        result = await retry_with_backoff(
            storage_service.upload_file,
            max_retries=3,
            file_content=data,
            object_name="path/to/file.jpg"
        )
        ```
    """
    last_exception = None
    delay = initial_delay
    
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e
            if attempt < max_retries - 1:
                logger.warning(
                    f"Retry attempt {attempt + 1}/{max_retries} failed: {type(e).__name__}",
                    extra={
                        "event": "retry",
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "error_type": type(e).__name__,
                        "error_message": str(e)[:100],
                    }
                )
                await asyncio.sleep(delay)
                delay = min(delay * exponential_base, max_delay)
            else:
                logger.error(
                    f"All retry attempts failed: {type(e).__name__}",
                    extra={
                        "event": "retry",
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "error_type": type(e).__name__,
                        "error_message": str(e)[:100],
                    }
                )
        except Exception as e:
            # 재시도 불가능한 예외는 즉시 전파
            logger.error(
                f"Non-retryable exception: {type(e).__name__}",
                extra={
                    "event": "retry",
                    "error_type": type(e).__name__,
                    "error_message": str(e)[:100],
                }
            )
            raise
    
    if last_exception:
        raise last_exception
    else:
        raise RuntimeError("Retry failed without exception")
