"""
설정 검증 유틸리티.

애플리케이션 시작 시 필수 설정을 검증합니다.
프로덕션 환경에서만 실행됩니다.
"""
import logging
from typing import List, Tuple

from sqlalchemy import text

from app.config import get_settings, Environment
from app.database import engine

logger = logging.getLogger("app.config_validator")


async def validate_configuration() -> None:
    """
    애플리케이션 설정을 검증합니다.
    
    프로덕션 환경에서만 실행됩니다.
    검증 실패 시 예외를 발생시켜 애플리케이션 시작을 중단합니다.
    """
    settings = get_settings()
    
    # 개발 환경에서는 스킵
    if settings.environment != Environment.PRODUCTION:
        logger.info(
            "Config validation skipped (not production)",
            extra={"event": "config", "environment": settings.environment.value},
        )
        return
    
    logger.info(
        "Starting configuration validation",
        extra={"event": "config"},
    )
    
    errors: List[str] = []
    
    # DB 연결 테스트
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection: OK", extra={"event": "config"})
    except Exception as e:
        error_msg = f"Database connection failed: {str(e)}"
        errors.append(error_msg)
        logger.error(error_msg, extra={"event": "config"}, exc_info=True)
    
    # Object Storage 설정 검증
    storage_errors = _validate_storage_config(settings)
    errors.extend(storage_errors)
    
    # CDN 설정 검증 (선택적)
    cdn_errors = _validate_cdn_config(settings)
    errors.extend(cdn_errors)
    
    # 에러가 있으면 예외 발생
    if errors:
        error_summary = "\n".join(f"  - {e}" for e in errors)
        raise ValueError(
            f"Configuration validation failed:\n{error_summary}\n"
            "Please check your environment variables and configuration."
        )
    
    logger.info(
        "Configuration validation completed successfully",
        extra={"event": "config"},
    )


def _validate_storage_config(settings) -> List[str]:
    """Object Storage 설정 검증."""
    errors: List[str] = []
    
    # IAM 인증 정보 확인
    iam_user = settings.nhn_storage_iam_user or settings.nhn_storage_username
    iam_password = settings.nhn_storage_iam_password or settings.nhn_storage_password
    tenant_id = settings.nhn_storage_tenant_id or settings.nhn_storage_project_id
    
    if not iam_user:
        errors.append("NHN_STORAGE_IAM_USER or NHN_STORAGE_USERNAME is required")
    
    if not iam_password:
        errors.append("NHN_STORAGE_IAM_PASSWORD or NHN_STORAGE_PASSWORD is required")
    
    if not tenant_id:
        errors.append("NHN_STORAGE_TENANT_ID or NHN_STORAGE_PROJECT_ID is required")
    
    if not settings.nhn_storage_container:
        errors.append("NHN_STORAGE_CONTAINER is required")
    
    # S3 API 자격 증명 확인 (Presigned URL 사용 시)
    if not settings.nhn_s3_access_key:
        logger.warning(
            "NHN_S3_ACCESS_KEY not set (presigned URL will not work)",
            extra={"event": "config"},
        )
    
    if not settings.nhn_s3_secret_key:
        logger.warning(
            "NHN_S3_SECRET_KEY not set (presigned URL will not work)",
            extra={"event": "config"},
        )
    
    if errors:
        logger.error(
            "Object Storage configuration validation failed",
            extra={"event": "config", "errors": errors},
        )
    else:
        logger.info("Object Storage configuration: OK", extra={"event": "config"})
    
    return errors


def _validate_cdn_config(settings) -> List[str]:
    """CDN 설정 검증 (선택적)."""
    errors: List[str] = []
    
    # CDN은 선택적이므로 설정이 없어도 에러가 아님
    if not settings.nhn_cdn_domain:
        logger.info(
            "CDN not configured (optional)",
            extra={"event": "config"},
        )
        return errors
    
    # CDN 도메인이 있으면 App Key도 필요
    if not settings.nhn_cdn_app_key:
        errors.append("NHN_CDN_APP_KEY is required when NHN_CDN_DOMAIN is set")
    
    if not settings.nhn_cdn_secret_key and not settings.nhn_cdn_encrypt_key:
        errors.append(
            "NHN_CDN_SECRET_KEY or NHN_CDN_ENCRYPT_KEY is required when CDN is configured"
        )
    
    if errors:
        logger.error(
            "CDN configuration validation failed",
            extra={"event": "config", "errors": errors},
        )
    else:
        logger.info("CDN configuration: OK", extra={"event": "config"})
    
    return errors
