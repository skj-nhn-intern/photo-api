"""
NHN Cloud Log & Crash service integration.

역할: NHN Cloud Log & Crash로 로그를 비동기 전송
참고: 로컬 로깅(파일/stdout)은 Python 표준 로거(logger.py)가 처리

운영 로깅은 Python 표준 로거를 직접 사용하고,
NHN Cloud 전송이 필요한 경우에만 이 서비스를 사용.
"""
import asyncio
import json
import logging
import traceback
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from collections import deque
import platform
import socket

import httpx

from app.config import get_settings
from app.utils.prometheus_metrics import (
    external_request_errors_total,
    record_external_request,
)


class LogLevel(str, Enum):
    """Log levels matching NHN Cloud Log & Crash API."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"


# 로깅에서 제외할 개인정보 필드
_SENSITIVE_FIELDS = frozenset({"email", "username", "password", "token", "secret"})


class NHNLoggerService:
    """
    NHN Cloud Log & Crash 전송 서비스.
    
    특징:
    - 비동기 큐 기반 전송 (논블로킹)
    - 배치 처리로 효율성 확보
    - 실패 시 재시도
    - 큐 크기 제한으로 메모리 안전
    
    주의: 로컬 로깅(파일/stdout)은 Python 표준 로거가 처리.
    이 서비스는 NHN Cloud 전송만 담당.
    """
    
    MAX_QUEUE_SIZE = 10000
    BATCH_SIZE = 100
    FLUSH_INTERVAL = 5.0  # seconds
    MAX_RETRIES = 3
    
    def __init__(self):
        self.settings = get_settings()
        self._queue: deque = deque(maxlen=self.MAX_QUEUE_SIZE)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._hostname = socket.gethostname()
        self._platform = platform.system()
        self._logger = logging.getLogger("app.nhn_logger")
    
    def queue_size(self) -> int:
        """Current log queue length (for Prometheus / backpressure monitoring)."""
        return len(self._queue)

    async def start(self) -> None:
        """Start the background log processing task."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._process_queue())
    
    async def stop(self) -> None:
        """Stop the logger and flush remaining logs."""
        self._running = False
        
        if self._task:
            await self._flush_all()
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
    
    def _filter_sensitive(self, data: dict) -> dict:
        """개인정보 필드 제거."""
        return {k: v for k, v in data.items() if k not in _SENSITIVE_FIELDS}
    
    def _create_log_body(
        self,
        level: LogLevel,
        message: str,
        **extra: Any,
    ) -> dict:
        """Create a log message body following NHN Cloud API format."""
        body = {
            "projectName": self.settings.nhn_log_appkey,
            "projectVersion": self.settings.app_version,
            "logVersion": self.settings.nhn_log_version,
            "body": message,
            "logLevel": level.value,
            "logSource": "API",
            "logType": "log",
            "host": self._hostname,
            "platform": self._platform,
            "sendTime": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        }
        
        # 개인정보 제거 후 추가 필드 포함
        if extra:
            filtered = self._filter_sensitive(extra)
            if filtered:
                body["customFields"] = json.dumps(filtered)
        
        return body
    
    def _enqueue(self, level: LogLevel, message: str, **extra: Any) -> None:
        """NHN Cloud 큐에 로그 추가 (로컬 로깅 없음)."""
        log_body = self._create_log_body(level, message, **extra)
        self._queue.append(log_body)
    
    def debug(self, message: str, **extra: Any) -> None:
        """NHN Cloud에 DEBUG 로그 전송."""
        self._enqueue(LogLevel.DEBUG, message, **extra)
    
    def info(self, message: str, **extra: Any) -> None:
        """NHN Cloud에 INFO 로그 전송."""
        self._enqueue(LogLevel.INFO, message, **extra)
    
    def warn(self, message: str, **extra: Any) -> None:
        """NHN Cloud에 WARN 로그 전송."""
        self._enqueue(LogLevel.WARN, message, **extra)
    
    def error(self, message: str, **extra: Any) -> None:
        """NHN Cloud에 ERROR 로그 전송."""
        self._enqueue(LogLevel.ERROR, message, **extra)
    
    def fatal(self, message: str, **extra: Any) -> None:
        """NHN Cloud에 FATAL 로그 전송."""
        self._enqueue(LogLevel.FATAL, message, **extra)
    
    def exception(self, message: str, exc: Exception, **extra: Any) -> None:
        """NHN Cloud에 예외 로그 전송 (traceback 포함)."""
        tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
        extra["exception_type"] = type(exc).__name__
        extra["traceback"] = "".join(tb)
        self.error(message, **extra)
    
    async def _send_logs(self, logs: list[dict]) -> bool:
        """
        Send a batch of logs to NHN Cloud.

        Args:
            logs: List of log message bodies

        Returns:
            True if send was successful
        """
        if not logs or not self.settings.nhn_log_appkey:
            return True

        url = self.settings.nhn_log_url

        async with record_external_request("nhn_log"):
            for attempt in range(self.MAX_RETRIES):
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        # Send each log individually (API requirement)
                        for log in logs:
                            response = await client.post(
                                url,
                                json=log,
                                headers={
                                    "Content-Type": "application/json",
                                },
                            )
                            # Log API returns 200 on success
                            if response.status_code != 200:
                                continue

                        return True

                except Exception as e:
                    if attempt < self.MAX_RETRIES - 1:
                        await asyncio.sleep(1 * (attempt + 1))
                        continue
                    # Final attempt failed, logs will be lost — 서버에 기록 (NHN 로거 사용 금지, 재귀 방지)
                    external_request_errors_total.labels(service="nhn_log").inc()
                    logging.getLogger("app").error(
                        "NHN Log send failed after retries",
                        extra={"event": "nhn_log", "error": str(e), "batch_size": len(logs)},
                    )
                    return False

            external_request_errors_total.labels(service="nhn_log").inc()
            logging.getLogger("app").error(
                "NHN Log send failed (non-200)",
                extra={"event": "nhn_log", "batch_size": len(logs)},
            )
            return False
    
    async def _process_queue(self) -> None:
        """Background task that processes the log queue."""
        while self._running:
            try:
                await asyncio.sleep(self.FLUSH_INTERVAL)
                await self._flush_batch()
            except asyncio.CancelledError:
                break
            except Exception:
                # Don't let logger errors crash the application
                pass
    
    async def _flush_batch(self) -> None:
        """Flush a batch of logs from the queue."""
        if not self._queue:
            return
        
        batch = []
        while self._queue and len(batch) < self.BATCH_SIZE:
            try:
                batch.append(self._queue.popleft())
            except IndexError:
                break
        
        if batch:
            await self._send_logs(batch)
    
    async def _flush_all(self) -> None:
        """Flush all remaining logs in the queue."""
        while self._queue:
            await self._flush_batch()


# Singleton instance
_logger_service: Optional[NHNLoggerService] = None


def get_logger_service() -> NHNLoggerService:
    """Get the singleton logger service instance."""
    global _logger_service
    if _logger_service is None:
        _logger_service = NHNLoggerService()
    return _logger_service
