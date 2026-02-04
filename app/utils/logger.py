"""
운영 환경용 Python 로깅 설정.

원칙:
- INFO: 중요 비즈니스 이벤트 (가입, 업로드, 공유링크 생성)
- WARNING: 클라이언트 오류 (잘못된 인증, 만료된 링크)
- ERROR: 시스템 오류, 외부 서비스 실패
- 개인정보 제외 (email, username 등은 로깅하지 않음)

로그 출력:
- stdout: 사람이 읽기 쉬운 텍스트 (journald)
- /var/log/photo-api/*.log: NDJSON (Promtail → Loki)
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

# 로깅에서 제외할 개인정보 필드
_SENSITIVE_FIELDS = frozenset({"email", "username", "password", "token", "secret"})


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
    운영용 NDJSON 포맷터.
    
    출력 필드:
    - ts: 타임스탬프
    - level: 로그 레벨
    - event: 이벤트 타입 (lifecycle, request, auth, photo, share, storage, cdn)
    - msg: 메시지
    - ctx: 추가 컨텍스트 (개인정보 제외)
    - exc: 예외 정보 (에러 시)
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
        }
        
        # event 필드 우선 배치
        if getattr(record, "event", None):
            payload["event"] = record.event
        
        payload["msg"] = record.getMessage()
        
        # 추가 컨텍스트 (개인정보 제외)
        extra_ctx = {
            k: v for k, v in record.__dict__.items()
            if k not in _STANDARD_ATTRS 
            and k != "event" 
            and k not in _SENSITIVE_FIELDS
            and v is not None
        }
        if extra_ctx:
            payload["ctx"] = extra_ctx
        
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    """
    운영 환경용 로깅 설정.
    
    - stdout: 텍스트 포맷 (journald)
    - /var/log/photo-api/app.log: INFO 이상 NDJSON
    - /var/log/photo-api/error.log: ERROR 이상 NDJSON
    - 외부 라이브러리 로그 억제 (httpx, httpcore, asyncio 등)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)
    root_logger.handlers.clear()

    # stdout: 사람이 읽기 쉬운 형식 (journald)
    text_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(text_formatter)
    root_logger.addHandler(stdout_handler)

    # stderr: ERROR 이상만
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(text_formatter)
    root_logger.addHandler(stderr_handler)

    # 파일 로그: NDJSON (Promtail → Loki)
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
        root_logger.warning("File logging disabled: %s", e)
    
    # 외부 라이브러리 로그 억제 (운영에서 노이즈 방지)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
