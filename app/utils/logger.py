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

장애 대응:
- Request ID: 요청 추적을 위한 고유 식별자
- Instance IP: 멀티 인스턴스 환경에서 출처 식별
"""
import contextvars
import json
import logging
import socket
import sys
import uuid
from datetime import timezone
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional

from app.config import get_settings

settings = get_settings()

# Promtail의 __path__: /var/log/photo-api/*.log 와 동일해야 함
LOG_DIR = Path("/var/log/photo-api")

# 로깅에서 제외할 개인정보 필드
_SENSITIVE_FIELDS = frozenset({"email", "username", "password", "token", "secret"})

# Request ID를 저장하는 context variable (비동기 안전)
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)


def _get_instance_ip() -> str:
    """환경변수 INSTANCE_IP 사용. 없으면 hostname -I 첫 번째 값."""
    ip = (get_settings().instance_ip or "").strip()
    if ip:
        return ip
    try:
        import subprocess
        r = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if r.returncode == 0 and r.stdout:
            first = r.stdout.strip().split()
            if first:
                return first[0]
    except Exception:
        pass
    return socket.gethostname()


# 인스턴스 IP (env 또는 hostname -I)
INSTANCE_IP = _get_instance_ip()


def generate_request_id() -> str:
    """새 Request ID 생성. 짧고 읽기 쉬운 형식."""
    return uuid.uuid4().hex[:12]


def get_request_id() -> Optional[str]:
    """현재 Request ID 반환."""
    return request_id_var.get()


def set_request_id(request_id: Optional[str] = None) -> str:
    """Request ID 설정. None이면 새로 생성."""
    rid = request_id or generate_request_id()
    request_id_var.set(rid)
    return rid


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
    - instance: 인스턴스 IP (멀티 인스턴스 식별)
    - rid: Request ID (요청 추적)
    - event: 이벤트 타입 (lifecycle, request, auth, photo, share, storage, cdn)
    - msg: 메시지
    - ctx: 추가 컨텍스트 (개인정보 제외)
    - exc: 예외 정보 (에러 시)
    """

    def format(self, record: logging.LogRecord) -> str:
        # UTC ISO8601 (Loki/Promtail 파싱용, 타임존 오차 방지)
        from datetime import datetime
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        try:
            msecs = int(getattr(record, "msecs", 0) or 0) % 1000
        except (TypeError, ValueError):
            msecs = 0
        ts_utc = dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{msecs:03d}Z"
        payload = {
            "ts": ts_utc,
            "level": record.levelname,
            "instance": INSTANCE_IP,
        }
        
        # Request ID (있으면 포함)
        rid = get_request_id()
        if rid:
            payload["rid"] = rid
        
        # event 필드 우선 배치
        if getattr(record, "event", None):
            payload["event"] = record.event
        
        payload["msg"] = record.getMessage()
        
        # 추가 컨텍스트 (상위 필드·개인정보 제외)
        _skip_in_ctx = _STANDARD_ATTRS | {"event", "instance"}  # 상위에 이미 있음
        extra_ctx = {
            k: v for k, v in record.__dict__.items()
            if k not in _skip_in_ctx
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
    
    # SQLAlchemy 로그 억제 (느린 쿼리는 app.db에서 별도 로깅)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.dialects").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.orm").setLevel(logging.WARNING)
