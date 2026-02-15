"""
Configuration validation on startup.

Startup 시 설정을 검증하여 런타임 에러를 방지합니다.
"""
import logging
from typing import Optional

from app.config import get_settings
from app.database import get_db_context
from sqlalchemy import select

logger = logging.getLogger("app.config_validator")
settings = get_settings()


async def validate_database_connection() -> tuple[bool, Optional[str]]:
    """
    데이터베이스 연결을 테스트합니다.
    
    Returns:
        (성공 여부, 에러 메시지)
    """
    try:
        async with get_db_context() as db:
            await db.execute(select(1))
        return True, None
    except Exception as e:
        error_msg = f"Database connection failed: {str(e)[:200]}"
        logger.error(error_msg, exc_info=True, extra={"event": "config_validation"})
        return False, error_msg


async def validate_object_storage_config() -> tuple[bool, Optional[str]]:
    """
    Object Storage 설정을 검증합니다.
    
    Returns:
        (성공 여부, 에러 메시지)
    """
    try:
        # 필수 설정 확인
        if not settings.nhn_storage_iam_user and not settings.nhn_storage_username:
            return False, "NHN_STORAGE_IAM_USER or NHN_STORAGE_USERNAME is required"
        
        if not settings.nhn_storage_iam_password and not settings.nhn_storage_password:
            return False, "NHN_STORAGE_IAM_PASSWORD or NHN_STORAGE_PASSWORD is required"
        
        if not settings.nhn_storage_tenant_id and not settings.nhn_storage_project_id:
            return False, "NHN_STORAGE_TENANT_ID or NHN_STORAGE_PROJECT_ID is required"
        
        if not settings.nhn_storage_url:
            return False, "NHN_STORAGE_URL is required"
        
        if not settings.nhn_storage_container:
            return False, "NHN_STORAGE_CONTAINER is required"
        
        # 실제 인증 테스트는 선택적 (startup 시간 증가)
        # 필요 시 주석 해제
        # from app.services.nhn_object_storage import get_storage_service
        # storage = get_storage_service()
        # await storage._get_auth_token()
        
        return True, None
    except Exception as e:
        error_msg = f"Object Storage configuration validation failed: {str(e)[:200]}"
        logger.error(error_msg, exc_info=True, extra={"event": "config_validation"})
        return False, error_msg


async def validate_cdn_config() -> tuple[bool, Optional[str]]:
    """
    CDN 설정을 검증합니다 (선택적).
    
    Returns:
        (성공 여부, 에러 메시지)
    """
    # CDN은 선택적이므로 설정이 없어도 OK
    if not settings.nhn_cdn_domain or not settings.nhn_cdn_app_key:
        logger.info("CDN not configured (optional)", extra={"event": "config_validation"})
        return True, None
    
    try:
        # 필수 설정 확인
        if not settings.nhn_cdn_secret_key and not settings.nhn_cdn_encrypt_key:
            return False, "NHN_CDN_SECRET_KEY or NHN_CDN_ENCRYPT_KEY is required when CDN is enabled"
        
        return True, None
    except Exception as e:
        error_msg = f"CDN configuration validation failed: {str(e)[:200]}"
        logger.error(error_msg, exc_info=True, extra={"event": "config_validation"})
        return False, error_msg


async def validate_all_config() -> tuple[bool, list[str]]:
    """
    모든 설정을 검증합니다.
    
    Returns:
        (모든 검증 통과 여부, 에러 메시지 리스트)
    """
    errors = []
    
    # DB 연결 테스트
    db_ok, db_error = await validate_database_connection()
    if not db_ok:
        errors.append(db_error)
    
    # Object Storage 설정 검증
    storage_ok, storage_error = await validate_object_storage_config()
    if not storage_ok:
        errors.append(storage_error)
    
    # CDN 설정 검증 (선택적)
    cdn_ok, cdn_error = await validate_cdn_config()
    if not cdn_ok:
        errors.append(cdn_error)
    
    return len(errors) == 0, errors
