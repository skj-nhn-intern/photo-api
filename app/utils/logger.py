"""
Python logging configuration for file and journald output.
Supports both file logging (for Logstash) and stdout (for journald).
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from app.config import get_settings

settings = get_settings()


def setup_logging() -> None:
    """
    Configure Python logging to write to both:
    - stdout/stderr (captured by journald)
    - File (for Logstash)
    """
    # 로그 디렉토리 생성
    log_dir = Path("/var/log/photo-api")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)
    
    # 기존 핸들러 제거 (중복 방지)
    root_logger.handlers.clear()
    
    # 로그 포맷
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 1. stdout 핸들러 (journald로 전달)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)
    
    # 2. stderr 핸들러 (에러 로그, journald로 전달)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(formatter)
    root_logger.addHandler(stderr_handler)
    
    # 3. 파일 핸들러 - 애플리케이션 로그 (Logstash 전송용)
    app_log_file = log_dir / "app.log"
    file_handler = RotatingFileHandler(
        app_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # 4. 파일 핸들러 - 에러 로그 (Logstash 전송용)
    error_log_file = log_dir / "error.log"
    error_handler = RotatingFileHandler(
        error_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
    # uvicorn 로거 설정
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.setLevel(logging.INFO)
    
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.setLevel(logging.INFO)
