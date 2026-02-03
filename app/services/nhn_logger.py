"""
NHN Cloud Log & Crash service integration.
Provides async logging that doesn't block the main application.
Uses a background queue to batch log messages for efficiency.
동시에 Python 표준 로거로도 전달해 파일/스토드아웃(Promtail→Loki)에 동일 이벤트 기록.
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


class NHNLoggerService:
    """
    Async logger service for NHN Cloud Log & Crash.
    
    Features:
    - Non-blocking async logging
    - Background queue processing
    - Automatic batching of log messages
    - Retry mechanism for failed sends
    - Memory-safe with queue size limits
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
            # Give time to flush remaining logs
            await self._flush_all()
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
    
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
        
        # Add extra fields
        if extra:
            body["customFields"] = json.dumps(extra)
        
        return body
    
    def log(
        self,
        level: LogLevel,
        message: str,
        **extra: Any,
    ) -> None:
        """
        Add a log message to the queue and to Python logger (file/stdout).
        Non-blocking; one event for NHN Cloud and local logs.
        """
        log_body = self._create_log_body(level, message, **extra)
        self._queue.append(log_body)

        # 동일 이벤트를 파일/스토드아웃에도 기록 (Promtail→Loki, 장애 대응용)
        _LEVEL_MAP = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARN: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.FATAL: logging.CRITICAL,
        }
        py_level = _LEVEL_MAP.get(level, logging.INFO)
        std_logger = logging.getLogger("app")
        std_logger.log(py_level, message, extra=extra)
    
    def debug(self, message: str, **extra: Any) -> None:
        """Log a debug message."""
        self.log(LogLevel.DEBUG, message, **extra)
    
    def info(self, message: str, **extra: Any) -> None:
        """Log an info message."""
        self.log(LogLevel.INFO, message, **extra)
    
    def warn(self, message: str, **extra: Any) -> None:
        """Log a warning message."""
        self.log(LogLevel.WARN, message, **extra)
    
    def error(self, message: str, **extra: Any) -> None:
        """Log an error message."""
        self.log(LogLevel.ERROR, message, **extra)
    
    def fatal(self, message: str, **extra: Any) -> None:
        """Log a fatal message."""
        self.log(LogLevel.FATAL, message, **extra)
    
    def exception(self, message: str, exc: Exception, **extra: Any) -> None:
        """Log an exception with traceback (NHN + Python logger)."""
        tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
        extra["exception_type"] = type(exc).__name__
        extra["exception_message"] = str(exc)
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


# Convenience functions for direct logging
def log_debug(message: str, **extra: Any) -> None:
    """Log a debug message."""
    get_logger_service().debug(message, **extra)


def log_info(message: str, **extra: Any) -> None:
    """Log an info message."""
    get_logger_service().info(message, **extra)


def log_warn(message: str, **extra: Any) -> None:
    """Log a warning message."""
    get_logger_service().warn(message, **extra)


def log_error(message: str, **extra: Any) -> None:
    """Log an error message."""
    get_logger_service().error(message, **extra)


def log_exception(message: str, exc: Exception, **extra: Any) -> None:
    """Log an exception with traceback."""
    get_logger_service().exception(message, exc, **extra)
