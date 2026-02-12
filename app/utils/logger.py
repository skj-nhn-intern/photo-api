"""
운영 환경용 Python 구조화된 로깅 설정.

로그 레벨 전략:
- ERROR: 즉시 대응 필요한 오류 (DB 연결 실패, 외부 API 장애)
- WARN: 잠재적 문제, 곧 이슈가 될 수 있음 (재시도 발생, 임계치 근접)
- INFO: 주요 비즈니스 이벤트 (주문 완료, 사용자 로그인)
- DEBUG: 개발/디버깅용 상세 정보 (함수 진입/종료, 변수 값)

구조화된 로깅:
- JSON 형식의 구조화된 로그
- 필수 필드: timestamp, level, service, message
- 인프라 컨텍스트: host, instance_ip, environment, region, version
- 요청 컨텍스트: http_method, http_path, http_status, duration_ms, client_ip, user_agent
- 오류 필드: error_type, error_message, stack_trace, error_code, retry_count, upstream_service

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

# 로그 디렉터리: 설정값 → /var/log/photo-api. setup_logging()에서 쓰기 실패 시 ./logs 로 fallback
def _resolve_log_dir() -> Path:
    if getattr(settings, "log_dir", None) and str(settings.log_dir).strip():
        return Path(settings.log_dir).resolve()
    return Path("/var/log/photo-api")


LOG_DIR = _resolve_log_dir()

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
    구조화된 로깅을 위한 NDJSON 포맷터.
    
    필수 필드:
    - timestamp: ISO 8601 UTC 타임스탬프
    - level: 로그 심각도 (ERROR, WARN, INFO, DEBUG)
    - service: 서비스/애플리케이션 이름
    - message: 사람이 읽을 수 있는 설명
    
    인프라 컨텍스트:
    - host: 서버 호스트명 또는 IP
    - instance_ip: 인스턴스 IP (라벨 필터링용)
    - environment: prod, staging, dev 등
    - region: 배포 리전
    - version: 애플리케이션 버전 또는 커밋 해시
    
    요청 컨텍스트:
    - http_method: GET, POST 등
    - http_path: 요청 경로 (개인정보 제외)
    - http_status: 응답 상태 코드
    - duration_ms: 처리 소요 시간
    - client_ip: 클라이언트 IP
    - user_agent: 브라우저/클라이언트 정보
    - request_id: 요청 추적 ID
    
    오류 필드:
    - error_type: 예외 클래스명 또는 에러 코드
    - error_message: 오류 메시지
    - stack_trace: 스택 트레이스 (별도 필드로 분리)
    - error_code: 내부 정의 에러 코드
    - retry_count: 재시도 횟수
    - upstream_service: 오류 발생한 외부 서비스명
    """

    def format(self, record: logging.LogRecord) -> str:
        from datetime import datetime
        
        # 로그 타임스탬프: log_timezone(기본 Asia/Seoul) 또는 UTC. ISO8601 + 오프셋
        try:
            msecs = int(getattr(record, "msecs", 0) or 0) % 1000
        except (TypeError, ValueError):
            msecs = 0
        tz_name = (getattr(settings, "log_timezone", None) or "").strip()
        if tz_name:
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(tz_name)
            except Exception:
                tz = timezone.utc
        else:
            tz = timezone.utc
        dt = datetime.fromtimestamp(record.created, tz=tz)
        # RFC3339 형식 (Promtail format "2006-01-02T15:04:05.000Z07:00" 로 파싱)
        offset = dt.strftime("%z")
        if offset in ("", "+0000", "-0000"):
            suffix = "Z"
        else:
            suffix = f"{offset[:3]}:{offset[3:]}"
        timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{msecs:03d}{suffix}"
        
        # 필수 필드
        payload = {
            "timestamp": timestamp,
            "level": record.levelname,
            "service": settings.app_name,
            "message": record.getMessage(),
        }
        
        # 인프라 컨텍스트
        payload["host"] = INSTANCE_IP
        payload["instance_ip"] = getattr(record, "instance_ip", None) or INSTANCE_IP
        payload["environment"] = settings.environment.value.lower()
        payload["region"] = getattr(record, "region", None) or "kr1"
        payload["version"] = getattr(record, "version", None) or settings.app_version
        
        # 요청 컨텍스트
        if getattr(record, "http_method", None):
            payload["http_method"] = record.http_method
        if getattr(record, "http_path", None):
            payload["http_path"] = record.http_path
        if getattr(record, "http_status", None):
            payload["http_status"] = record.http_status
        if getattr(record, "duration_ms", None) is not None:
            payload["duration_ms"] = record.duration_ms
        if getattr(record, "client_ip", None):
            payload["client_ip"] = record.client_ip
        if getattr(record, "user_agent", None):
            payload["user_agent"] = record.user_agent
        
        # Request ID (요청 추적)
        rid = getattr(record, "request_id", None) or get_request_id()
        if rid:
            payload["request_id"] = rid
        
        # 오류 필드
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            payload["error_type"] = exc_type.__name__ if exc_type else "Unknown"
            payload["error_message"] = str(exc_value) if exc_value else ""
            payload["stack_trace"] = self.formatException(record.exc_info)
        
        if getattr(record, "error_type", None):
            payload["error_type"] = record.error_type
        if getattr(record, "error_message", None):
            payload["error_message"] = record.error_message
        if getattr(record, "error_code", None):
            payload["error_code"] = record.error_code
        if getattr(record, "retry_count", None) is not None:
            payload["retry_count"] = record.retry_count
        if getattr(record, "upstream_service", None):
            payload["upstream_service"] = record.upstream_service
        
        # 이벤트 타입 (기존 호환성)
        if getattr(record, "event", None):
            payload["event"] = record.event
        
        # 추가 컨텍스트 (상위 필드·개인정보 제외)
        _skip_fields = _STANDARD_ATTRS | {
            "event", "instance_ip", "environment", "region", "version",
            "http_method", "http_path", "http_status", "duration_ms",
            "client_ip", "user_agent", "request_id",
            "error_type", "error_message", "stack_trace", "error_code",
            "retry_count", "upstream_service"
        }
        extra_ctx = {
            k: v for k, v in record.__dict__.items()
            if k not in _skip_fields
            and k not in _SENSITIVE_FIELDS
            and v is not None
        }
        if extra_ctx:
            payload["context"] = extra_ctx
        
        return json.dumps(payload, ensure_ascii=False)


def log_with_context(
    level: int,
    message: str,
    *,
    # 요청 컨텍스트
    http_method: Optional[str] = None,
    http_path: Optional[str] = None,
    http_status: Optional[int] = None,
    duration_ms: Optional[float] = None,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_id: Optional[str] = None,
    # 오류 컨텍스트
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    error_code: Optional[str] = None,
    retry_count: Optional[int] = None,
    upstream_service: Optional[str] = None,
    # 인프라 컨텍스트
    region: Optional[str] = None,
    version: Optional[str] = None,
    instance_ip: Optional[str] = None,
    # 기타
    event: Optional[str] = None,
    exc_info: Optional[bool] = None,
    **extra
) -> None:
    """
    구조화된 로그를 남기는 헬퍼 함수.
    
    Args:
        level: 로그 레벨 (logging.INFO, logging.ERROR 등)
        message: 로그 메시지
        http_method: HTTP 메서드 (GET, POST 등)
        http_path: 요청 경로
        http_status: HTTP 상태 코드
        duration_ms: 처리 시간 (밀리초)
        client_ip: 클라이언트 IP
        user_agent: User-Agent
        request_id: 요청 ID
        error_type: 에러 타입
        error_message: 에러 메시지
        error_code: 내부 에러 코드
        retry_count: 재시도 횟수
        upstream_service: 외부 서비스명
        region: 리전
        version: 버전
        instance_ip: 인스턴스 IP (라벨 필터링용)
        event: 이벤트 타입
        exc_info: 예외 정보 포함 여부
        **extra: 추가 컨텍스트
    
    Example:
        log_with_context(
            logging.INFO,
            "User login successful",
            http_method="POST",
            http_path="/api/auth/login",
            http_status=200,
            duration_ms=123.45,
            client_ip="192.168.1.1",
            event="auth"
        )
    """
    logger = logging.getLogger(__name__)
    
    extra_dict = {
        "http_method": http_method,
        "http_path": http_path,
        "http_status": http_status,
        "duration_ms": duration_ms,
        "client_ip": client_ip,
        "user_agent": user_agent,
        "request_id": request_id,
        "error_type": error_type,
        "error_message": error_message,
        "error_code": error_code,
        "retry_count": retry_count,
        "upstream_service": upstream_service,
        "region": region,
        "version": version,
        "instance_ip": instance_ip,
        "event": event,
        **extra
    }
    
    # None 값 제거
    extra_dict = {k: v for k, v in extra_dict.items() if v is not None}
    
    logger.log(level, message, extra=extra_dict, exc_info=exc_info)


def log_error(
    message: str,
    *,
    error_type: Optional[str] = None,
    error_code: Optional[str] = None,
    upstream_service: Optional[str] = None,
    retry_count: Optional[int] = None,
    exc_info: bool = True,
    **extra
) -> None:
    """
    에러 로그를 남기는 헬퍼 함수.
    
    Args:
        message: 에러 메시지
        error_type: 에러 타입 (예: DatabaseError, APIError)
        error_code: 내부 에러 코드
        upstream_service: 오류 발생한 외부 서비스명
        retry_count: 재시도 횟수
        exc_info: 예외 정보 포함 여부 (기본: True)
        **extra: 추가 컨텍스트
    
    Example:
        try:
            db_connection.execute(query)
        except Exception as e:
            log_error(
                "Database connection failed",
                error_type="DatabaseError",
                error_code="DB_001",
                upstream_service="postgresql",
                exc_info=True
            )
    """
    log_with_context(
        logging.ERROR,
        message,
        error_type=error_type,
        error_code=error_code,
        upstream_service=upstream_service,
        retry_count=retry_count,
        exc_info=exc_info,
        **extra
    )


def log_warning(
    message: str,
    *,
    retry_count: Optional[int] = None,
    **extra
) -> None:
    """
    경고 로그를 남기는 헬퍼 함수.
    
    Args:
        message: 경고 메시지
        retry_count: 재시도 횟수
        **extra: 추가 컨텍스트
    
    Example:
        log_warning(
            "API rate limit approaching",
            retry_count=3,
            current_rate=950,
            limit=1000
        )
    """
    log_with_context(
        logging.WARNING,
        message,
        retry_count=retry_count,
        **extra
    )


def log_info(
    message: str,
    *,
    event: Optional[str] = None,
    **extra
) -> None:
    """
    정보 로그를 남기는 헬퍼 함수. 주요 비즈니스 이벤트에 사용.
    
    Args:
        message: 로그 메시지
        event: 이벤트 타입 (예: user_login, photo_upload, order_complete)
        **extra: 추가 컨텍스트
    
    Example:
        log_info(
            "User registration completed",
            event="user_registration",
            user_id=12345
        )
    """
    log_with_context(
        logging.INFO,
        message,
        event=event,
        **extra
    )


def log_debug(
    message: str,
    **extra
) -> None:
    """
    디버그 로그를 남기는 헬퍼 함수.
    
    Args:
        message: 디버그 메시지
        **extra: 추가 컨텍스트
    
    Example:
        log_debug(
            "Function entry",
            function="process_image",
            params={"width": 800, "height": 600}
        )
    """
    log_with_context(
        logging.DEBUG,
        message,
        **extra
    )


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

    # 파일 로그: NDJSON (Promtail → Loki). /var/log 권한 없으면 ./logs 로 fallback
    json_formatter = JsonLinesFormatter()
    log_dirs_to_try: list[Path] = [LOG_DIR]
    if LOG_DIR != Path.cwd() / "logs":
        log_dirs_to_try.append(Path.cwd() / "logs")
    for log_dir in log_dirs_to_try:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            app_log_file = log_dir / "app.log"
            error_log_file = log_dir / "error.log"
            app_log_file.touch(exist_ok=True)
            error_log_file.touch(exist_ok=True)

            fh = FlushingRotatingFileHandler(
                app_log_file,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            fh.setLevel(logging.INFO)
            fh.setFormatter(json_formatter)
            root_logger.addHandler(fh)

            eh = FlushingRotatingFileHandler(
                error_log_file,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            eh.setLevel(logging.ERROR)
            eh.setFormatter(json_formatter)
            root_logger.addHandler(eh)
            if log_dir != LOG_DIR:
                root_logger.warning(
                    "File logging using fallback directory: %s (primary %s not writable)",
                    log_dir,
                    LOG_DIR,
                )
            break
        except OSError as e:
            if log_dir == log_dirs_to_try[-1]:
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
