"""
Python logging configuration for file and stdout.
Logs go to stdout (journald) and file (/var/log/photo-api). Loki 수집은 Promtail이 파일을 읽어 처리.
"""
import json
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from app.config import get_settings

settings = get_settings()

# Promtail의 __path__: /var/log/photo-api/*.log 와 동일해야 함
LOG_DIR = Path("/var/log/photo-api")


class FlushingRotatingFileHandler(RotatingFileHandler):
    """매 로그마다 디스크에 flush. Promtail이 최신 줄을 바로 읽을 수 있도록 함."""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


# 로그 레코드의 표준 필드 (ctx에 넣지 않음)
_STANDARD_ATTRS = frozenset(
    {
        "name", "msg", "args", "created", "filename", "funcName",
        "levelname", "levelno", "lineno", "module", "msecs",
        "pathname", "process", "processName", "relativeCreated",
        "stack_info", "exc_info", "exc_text", "thread", "threadName",
        "message", "asctime", "taskName",
    }
)


class JsonLinesFormatter(logging.Formatter):
    """
    한 줄에 하나의 JSON 객체 (NDJSON).
    장애 대응용: ts, level, msg, event(선택), ctx(선택), exc(에러 시) 만 출력.
    Loki/Grafana에서 | json 후 event/level로 필터링.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        if getattr(record, "event", None):
            payload["event"] = record.event
        extra_ctx = {
            k: v for k, v in record.__dict__.items()
            if k not in _STANDARD_ATTRS and k != "event" and v is not None
        }
        if extra_ctx:
            payload["ctx"] = extra_ctx
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    """
    Configure Python logging to:
    - stdout/stderr (journald)
    - File (/var/log/photo-api/*.log) — Promtail이 이 파일을 읽어 Loki로 전송
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)
    root_logger.handlers.clear()

    # stdout/stderr: 사람이 읽기 쉬운 형식 (journald 등)
    text_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(text_formatter)
    root_logger.addHandler(stdout_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(text_formatter)
    root_logger.addHandler(stderr_handler)

    # 파일 로그: Loki/Grafana용 NDJSON (한 줄 = JSON 한 개). Promtail 경로와 일치 (conf/promtail-config.yaml)
    json_formatter = JsonLinesFormatter()
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        app_log_file = LOG_DIR / "app.log"
        error_log_file = LOG_DIR / "error.log"

        file_handler = FlushingRotatingFileHandler(
            app_log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(json_formatter)
        root_logger.addHandler(file_handler)

        error_handler = FlushingRotatingFileHandler(
            error_log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(json_formatter)
        root_logger.addHandler(error_handler)
    except OSError as e:
        # 권한/경로 문제 시 파일 로그만 비활성화, stdout은 유지
        root_logger.warning(
            "File logging disabled (Promtail/Loki will not see file logs): %s", e
        )
    
    # uvicorn: 앱 미들웨어에서 요청 로그를 한 번만 남기므로 access 중복 비활성화
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
