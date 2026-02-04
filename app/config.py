"""
Application configuration using Pydantic Settings.
Manages all environment variables and settings.
"""
from enum import Enum
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator


class Environment(str, Enum):
    """Application environment modes."""
    DEV = "DEV"
    PRODUCTION = "PRODUCTION"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Environment
    environment: Environment = Field(
        default=Environment.DEV,
        description="Application environment: DEV or PRODUCTION"
    )
    
    # Application
    app_name: str = Field(default="Photo API")
    app_version: str = Field(default="1.0.0")
    debug: bool = Field(default=False)
    secret_key: str = Field(default="change-me-in-production")
    
    @model_validator(mode='after')
    def set_debug_from_environment(self):
        """Set debug mode based on environment if not explicitly set via environment variable."""
        # DEBUG 환경 변수가 명시적으로 설정되지 않은 경우에만 환경 모드에 따라 설정
        import os
        if 'DEBUG' not in os.environ:
            self.debug = self.environment == Environment.DEV
        return self
    
    @property
    def is_dev(self) -> bool:
        """Check if running in development mode."""
        return self.environment == Environment.DEV
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == Environment.PRODUCTION
    
    # Database
    database_url: str = Field(default="sqlite+aiosqlite:///./photo_api.db")
    
    # JWT
    jwt_secret_key: str = Field(default="jwt-secret-change-in-production")
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30)
    
    # NHN Cloud Object Storage (IAM 인증 사용)
    nhn_storage_iam_user: str = Field(default="", description="IAM 사용자명 또는 API 사용자명")
    nhn_storage_iam_password: str = Field(default="", description="API 비밀번호 (Object Storage API 접근용, IAM 사용자 비밀번호와 다를 수 있음)")
    nhn_storage_project_id: str = Field(default="", description="IAM 프로젝트 ID")
    # 서비스 게이트웨이 사용 시: NHN 콘솔에서 내부(프라이빗) 엔드포인트 URL 확인 후 .env에 설정
    # 예: 내부 URL이 있다면 NHN_STORAGE_AUTH_URL=https://internal-identity.xxx/v2.0
    nhn_storage_auth_url: str = Field(
        default="https://api-identity-infrastructure.nhncloudservice.com/v2.0",
        description="IAM 인증 URL. 서비스 게이트웨이 사용 시 내부 엔드포인트로 설정"
    )
    nhn_storage_container: str = Field(default="photo-container")
    # 서비스 게이트웨이 사용 시 Object Storage 내부 URL로 설정 가능
    nhn_storage_url: str = Field(
        default="https://api-storage.nhncloudservice.com/v1",
        description="Object Storage URL. 서비스 게이트웨이 사용 시 내부 엔드포인트로 설정"
    )
    # Tenant ID (Object Storage Account에 사용)
    # IAM 인증 응답에서 자동 추출되지만, 명시적으로 설정할 수도 있음
    nhn_storage_tenant_id: str = Field(default="", description="Tenant ID (AUTH_{tenant_id} 형식에 사용). IAM 응답에서 자동 추출되지만 명시적으로 설정 가능")
    nhn_storage_username: str = Field(default="", description="레거시: nhn_storage_iam_user 사용")
    nhn_storage_password: str = Field(default="", description="레거시: nhn_storage_iam_password 사용")
    
    # NHN Cloud CDN (Auth Token API)
    # https://docs.nhncloud.com/ko/Contents%20Delivery/CDN/ko/api-guide-v2.0/#auth-token-api
    nhn_cdn_domain: str = Field(default="", description="CDN 도메인 (예: xxx.toastcdn.net)")
    nhn_cdn_app_key: str = Field(default="", description="CDN App Key")
    nhn_cdn_secret_key: str = Field(default="", description="CDN API Secret Key (API 인증용)")
    nhn_cdn_encrypt_key: str = Field(default="", description="CDN Token Encryption Key (토큰 생성용)")
    nhn_cdn_token_expire_seconds: int = Field(default=3600, description="Auth Token 유효 시간 (초)")
    
    # NHN Cloud Log & Crash
    nhn_log_appkey: str = Field(default="")
    nhn_log_url: str = Field(
        default="https://api-logncrash.nhncloudservice.com/v2/log"
    )
    nhn_log_version: str = Field(default="v2")
    nhn_log_platform: str = Field(default="API")
    
    # Prometheus (Observability). Loki 로그는 Promtail이 /var/log/photo-api 파일을 읽어 전송
    node_name: str = Field(default="", description="Node/Pod identifier for Prometheus labels")
    
    # 인스턴스 식별용 사설 IP (로그·메트릭용). 비우면 자동 감지(ip addr), 오토스케일 시 서버마다 다름
    instance_ip: str = Field(default="", description="서버 사설 IP (비우면 자동 감지)")
    
    # Loki (미사용·호환용). 로그는 Promtail로만 전송하므로 이 값은 사용하지 않음. .env에 남아 있어도 오류 없이 무시
    loki_url: str | None = Field(default=None, description="Deprecated: use Promtail for logs")
    loki_logs_labels: str | None = Field(default=None, description="Deprecated: use Promtail for logs")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Using lru_cache to avoid reading .env file on every request.
    """
    return Settings()
