"""
NHN Cloud CDN service integration.
Handles CDN URL generation with Auth Token authentication.

Auth Token API 참고:
https://docs.nhncloud.com/ko/Contents%20Delivery/CDN/ko/api-guide-v2.0/#auth-token-api
"""
import logging
import time
from typing import Optional, List

import httpx

from app.config import get_settings
from app.utils.prometheus_metrics import (
    external_request_errors_total,
    record_external_request,
)

logger = logging.getLogger("app.cdn")


class NHNCDNService:
    """
    Service for generating CDN URLs with Auth Token.
    NHN Cloud CDN Auth Token API를 사용하여 토큰을 생성합니다.
    
    Auth Token 생성 흐름:
    1. POST /v2.0/appKeys/{appKey}/auth-token 호출
    2. 응답에서 singlePathToken 추출
    3. URL에 ?token={token} 형태로 붙임
    """
    
    # NHN Cloud CDN API 엔드포인트
    CDN_API_URL = "https://cdn.api.nhncloudservice.com"
    
    def __init__(self):
        self.settings = get_settings()
        self._token_cache: dict[str, tuple[str, float]] = {}  # path -> (token, expire_time)
    
    async def _request_auth_token(
        self,
        path: str,
        duration_seconds: Optional[int] = None,
    ) -> Optional[str]:
        """
        NHN Cloud CDN API를 호출하여 Auth Token을 생성합니다.
        
        Args:
            path: CDN 경로 (예: "/photo/photos/1/xxx.jpg")
            duration_seconds: 토큰 유효 시간 (초)
            
        Returns:
            생성된 토큰 문자열, 실패시 None
        """
        if not self.settings.nhn_cdn_app_key:
            # App Key 미설정은 설정 오류가 아님 (CDN 미사용 환경)
            return None
        
        if duration_seconds is None:
            duration_seconds = self.settings.nhn_cdn_token_expire_seconds
        
        # Ensure path starts with /
        if not path.startswith("/"):
            path = f"/{path}"
        
        url = f"{self.CDN_API_URL}/v2.0/appKeys/{self.settings.nhn_cdn_app_key}/auth-token"
        
        # encryptKey: Token Encryption Key (encrypt_key가 없으면 secret_key 사용)
        encrypt_key = self.settings.nhn_cdn_encrypt_key or self.settings.nhn_cdn_secret_key
        
        payload = {
            "encryptKey": encrypt_key,
            "durationSeconds": duration_seconds,
            "singlePath": path,
        }
        
        # NHN Cloud API 인증 헤더 (Secret Key 사용)
        headers = {
            "Content-Type": "application/json",
        }
        # Secret Key가 있으면 Authorization 헤더 추가
        if self.settings.nhn_cdn_secret_key:
            headers["Authorization"] = self.settings.nhn_cdn_secret_key
        
        try:
            async with record_external_request("nhn_cdn"):
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, json=payload, headers=headers)

                    data = response.json()
                    if data.get("header", {}).get("isSuccessful"):
                        token = data.get("authToken", {}).get("singlePathToken")
                        return token
                    else:
                        logger.error(
                            "CDN auth token failed",
                            extra={"event": "cdn_token", "status": response.status_code},
                        )
                        external_request_errors_total.labels(service="nhn_cdn").inc()
                        return None

        except httpx.HTTPError as e:
            logger.error("CDN auth token API error", exc_info=e, extra={"event": "cdn_token"})
            external_request_errors_total.labels(service="nhn_cdn").inc()
            return None
    
    async def generate_auth_token_url(
        self,
        object_path: str,
        expires_in: Optional[int] = None,
    ) -> Optional[str]:
        """
        Generate a CDN URL with Auth Token for secure access.
        이미지 보기는 이 CDN Auth Token URL 또는 백엔드 스트리밍만 사용 (S3 GET presigned 미사용).
        
        **보안 보장:**
        - OBS URL을 절대 반환하지 않음
        - CDN Auth Token이 포함된 URL만 반환
        - 토큰이 없으면 CDN이 자동으로 접근 거부 (403 Forbidden)
        - 토큰은 짧은 유효기간을 가짐 (기본 120초)

        Args:
            object_path: The path to the object in storage (e.g., "image/2/uuid.png")
            expires_in: Token expiration time in seconds (default from settings)

        Returns:
            CDN URL with auth token, or None if CDN 미설정 or 토큰 발급 실패 (호출자는 스트리밍 fallback)
            ⚠️ 절대 OBS URL을 반환하지 않음. None 반환 시 백엔드 스트리밍 사용.
        """
        # CDN 미설정 시 None → 라우터에서 리다이렉트하지 않고 백엔드 스트리밍
        if not self.settings.nhn_cdn_domain or not self.settings.nhn_cdn_app_key:
            return None
        
        if expires_in is None:
            expires_in = self.settings.nhn_cdn_token_expire_seconds
        
        # CDN 경로 생성 (컨테이너 포함)
        # Object Storage 경로: photo/photo/image/{album_id}/{filename}
        # CDN 경로: /{container}/photo/photo/image/{album_id}/{filename}
        # 이렇게 하면 CDN 원본 설정에서 경로 변환이 필요 없음
        container = self.settings.nhn_storage_container
        if object_path.startswith("/"):
            object_path = object_path[1:]  # 앞의 / 제거
        
        # 컨테이너가 이미 경로에 포함되어 있는지 확인
        if object_path.startswith(f"{container}/"):
            cdn_path = f"/{object_path}"
        else:
            cdn_path = f"/{container}/{object_path}"
        
        # 캐시 확인
        cache_key = cdn_path
        if cache_key in self._token_cache:
            cached_token, expire_time = self._token_cache[cache_key]
            if time.time() < expire_time - 60:  # 1분 여유
                return f"https://{self.settings.nhn_cdn_domain}{cdn_path}?token={cached_token}"
        
        # Auth Token 생성 (CDN API 호출)
        token = await self._request_auth_token(cdn_path, expires_in)
        
        if token:
            self._token_cache[cache_key] = (token, time.time() + expires_in)
            return f"https://{self.settings.nhn_cdn_domain}{cdn_path}?token={token}"
        # 토큰 실패 시 None → 라우터에서 302 대신 백엔드 스트리밍 (SignatureDoesNotMatch/403 방지)
        logger.warning(
            "CDN auth token failed, caller should stream from backend",
            extra={"event": "cdn_token", "path": cdn_path},
        )
        return None

    def generate_auth_token_url_sync(
        self,
        object_path: str,
        expires_in: Optional[int] = None,
    ) -> str:
        """
        동기 버전: CDN URL 생성 (토큰 없이, Object Storage fallback)
        ⚠️ 주의: 이 메서드는 현재 사용되지 않습니다.
        PhotoService.get_photo_with_url는 항상 상대 경로(/photos/{id}/image)만 반환합니다.
        
        이 메서드는 레거시 코드이거나 향후 사용을 위해 남겨둔 것입니다.
        보안을 위해 OBS URL을 반환하지 않도록 주의하세요.
        
        CDN App Key가 없으면 Object Storage URL 반환 (보안 위험!)
        """
        # CDN 설정이 없으면 Object Storage URL 반환
        # ⚠️ 보안 경고: OBS URL을 반환하면 public OBS에 직접 접근 가능
        if not self.settings.nhn_cdn_domain or not self.settings.nhn_cdn_app_key:
            logger.warning(
                "generate_auth_token_url_sync: OBS URL 반환 (보안 위험)",
                extra={"event": "cdn_obs_fallback", "path": object_path}
            )
            return f"{self.settings.nhn_storage_url}/{self.settings.nhn_storage_container}/{object_path}"
        
        # CDN 경로 생성 (컨테이너 포함)
        container = self.settings.nhn_storage_container
        if object_path.startswith("/"):
            object_path = object_path[1:]  # 앞의 / 제거
        
        # 컨테이너가 이미 경로에 포함되어 있는지 확인
        if object_path.startswith(f"{container}/"):
            cdn_path = f"/{object_path}"
        else:
            cdn_path = f"/{container}/{object_path}"
        
        # 캐시에서 토큰 확인
        cache_key = cdn_path
        if cache_key in self._token_cache:
            cached_token, expire_time = self._token_cache[cache_key]
            if time.time() < expire_time - 60:
                return f"https://{self.settings.nhn_cdn_domain}{cdn_path}?token={cached_token}"
        
        # 캐시에 없으면 Object Storage URL 반환 (비동기 토큰 생성 필요)
        # ⚠️ 보안 경고: OBS URL을 반환하면 public OBS에 직접 접근 가능
        logger.warning(
            "generate_auth_token_url_sync: OBS URL 반환 (보안 위험, 토큰 캐시 없음)",
            extra={"event": "cdn_obs_fallback", "path": object_path}
        )
        return f"{self.settings.nhn_storage_url}/{self.settings.nhn_storage_container}/{object_path}"


# Singleton instance
_cdn_service: Optional[NHNCDNService] = None


def get_cdn_service() -> NHNCDNService:
    """Get the singleton CDN service instance."""
    global _cdn_service
    if _cdn_service is None:
        _cdn_service = NHNCDNService()
    return _cdn_service
