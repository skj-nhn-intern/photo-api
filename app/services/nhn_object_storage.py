"""
NHN Cloud Object Storage service integration.
Handles file upload, download, and deletion from Object Storage.

참조: https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/api-guide/
S3 API 참조: https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/s3-api-guide/
"""
import asyncio
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta

import httpx
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import get_settings
from app.utils.prometheus_metrics import record_external_request
from app.utils.logger import log_error, log_warning

logger = logging.getLogger("app.storage")


class NHNObjectStorageService:
    """
    Service for interacting with NHN Cloud Object Storage.
    Uses IAM (Identity and Access Management) authentication.
    
    컨테이너 관리 전략:
    1. 단일 컨테이너 사용 (photo-container)
    2. 사용자별 폴더 구조: photos/{user_id}/{filename}
    3. 컨테이너 자동 생성 (없을 경우)
    4. 토큰 캐싱 및 자동 갱신
    
    IAM 인증 방식:
    - IAM 사용자명과 비밀번호로 토큰 발급
    - 프로젝트 ID 기반 인증
    - Keystone v3 API 사용
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        self._storage_url: Optional[str] = None
        self._account: Optional[str] = None
        self._lock = asyncio.Lock()
        self._s3_client: Optional[boto3.client] = None
    
    async def _get_auth_token(self) -> str:
        """
        Get authentication token from NHN Cloud IAM service.
        Implements token caching and automatic refresh.
        
        IAM 인증 방식 사용 (Keystone v3 API)
        API 문서 참조: https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/api-guide/
        """
        # Check if current token is still valid (5분 여유)
        if (
            self._token 
            and self._token_expires 
            and datetime.utcnow() < self._token_expires - timedelta(minutes=5)
        ):
            return self._token
        
        # Acquire lock to prevent multiple simultaneous auth requests
        async with self._lock:
            # Double-check after acquiring lock
            if (
                self._token 
                and self._token_expires 
                and datetime.utcnow() < self._token_expires - timedelta(minutes=5)
            ):
                return self._token
            
            # IAM 인증 요청 형식 (Keystone v2 API)
            # NHN Cloud Object Storage는 v2.0 API를 사용
            # 문서: https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/api-guide/#_2
            iam_user = self.settings.nhn_storage_iam_user or self.settings.nhn_storage_username
            iam_password = self.settings.nhn_storage_iam_password or self.settings.nhn_storage_password
            tenant_id = self.settings.nhn_storage_tenant_id or self.settings.nhn_storage_project_id
            
            if not iam_user or not iam_password or not tenant_id:
                raise Exception("IAM 인증 정보가 설정되지 않았습니다. IAM 사용자명, 비밀번호, Tenant ID를 확인하세요.")
            
            # v2.0 API 엔드포인트 사용
            # 문서 기준: POST https://api-identity-infrastructure.nhncloudservice.com/v2.0/tokens
            if '/v3' in self.settings.nhn_storage_auth_url:
                auth_url = f"{self.settings.nhn_storage_auth_url.replace('/v3', '/v2.0')}/tokens"
            else:
                auth_url = f"{self.settings.nhn_storage_auth_url}/tokens"
            
            # Keystone v2 API 형식 (문서 참조)
            auth_data = {
                "auth": {
                    "tenantId": tenant_id,
                    "passwordCredentials": {
                        "username": iam_user,
                        "password": iam_password
                    }
                }
            }
            
            try:
                async with record_external_request("nhn_storage"):
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(
                            auth_url,
                            json=auth_data,
                            headers={"Content-Type": "application/json"},
                        )
                    
                    # 응답 상태 코드 확인
                    status_code = response.status_code
                    
                    # 응답 본문 파싱
                    try:
                        data = response.json()
                    except Exception as parse_error:
                        log_error(
                            "IAM authentication response parsing failed",
                            error_type="ResponseParseError",
                            error_code="STORAGE_001",
                            upstream_service="nhn_storage_iam",
                            http_status=status_code,
                            event="storage",
                            exc_info=True,
                        )
                        raise Exception("IAM 인증 응답을 파싱할 수 없습니다.")
                    
                    # 상태 코드가 200이 아니면 에러 처리
                    if status_code != 200:
                        error_message = "IAM 인증에 실패했습니다."
                        error_code = "STORAGE_002"
                        try:
                            error_detail = data.get("error", {})
                            if isinstance(error_detail, dict):
                                error_msg = error_detail.get("message", "")
                                if "Could not find" in error_msg or "tenant" in error_msg.lower():
                                    error_message = f"IAM 인증 실패: Tenant ID를 찾을 수 없습니다."
                                    error_code = "STORAGE_002_TENANT"
                                elif "Unauthorized" in error_msg or status_code == 401:
                                    error_message = "IAM 인증 실패: 인증 정보가 올바르지 않습니다."
                                    error_code = "STORAGE_002_AUTH"
                        except Exception:
                            pass
                        
                        log_error(
                            "IAM authentication failed",
                            error_type="AuthenticationError",
                            error_message=error_message,
                            error_code=error_code,
                            upstream_service="nhn_storage_iam",
                            http_status=status_code,
                            event="storage",
                            exc_info=False,
                        )
                        raise Exception(error_message)
                    
                    # Keystone v2 API 응답 형식
                    # 응답 본문에서 토큰 정보 추출 (이미 파싱됨)
                    access = data.get("access", {})
                    token_data = access.get("token", {})
                    
                    # 토큰 ID 추출
                    self._token = token_data.get("id")
                    if not self._token:
                        log_error(
                            "IAM token not found in response",
                            error_type="TokenError",
                            error_code="STORAGE_003",
                            upstream_service="nhn_storage_iam",
                            event="storage",
                            exc_info=False,
                        )
                        raise Exception("IAM 토큰을 받을 수 없습니다.")
                    
                    # 토큰 만료 시간 추출
                    expires_str = token_data.get("expires")
                    if expires_str:
                        # v2 API는 ISO 8601 형식 사용
                        self._token_expires = datetime.fromisoformat(
                            expires_str.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    else:
                        # 만료 시간이 없으면 24시간 후로 설정
                        self._token_expires = datetime.utcnow() + timedelta(hours=24)
                    
                    # 스토리지 계정(Account) 추출
                    # v2 API 응답에서 tenant 정보 추출
                    tenant_info = token_data.get("tenant", {})
                    tenant_id_from_response = tenant_info.get("id")
                    
                    # Tenant ID가 없으면 설정값 사용
                    if not tenant_id_from_response:
                        tenant_id_from_response = tenant_id
                    
                    if not tenant_id_from_response:
                        log_error(
                            "IAM tenant ID not found in response",
                            error_type="TenantError",
                            error_code="STORAGE_004",
                            upstream_service="nhn_storage_iam",
                            event="storage",
                            exc_info=False,
                        )
                        raise Exception("Tenant ID를 찾을 수 없습니다. NHN_STORAGE_TENANT_ID를 설정하세요.")
                    
                    self._account = f"AUTH_{tenant_id_from_response}"
                    self._storage_url = self.settings.nhn_storage_url
                    # 토큰 갱신 성공은 로깅 안 함 (정상 동작)
                    return self._token
                    
            except httpx.HTTPStatusError as e:
                log_error(
                    "Storage authentication HTTP error",
                    error_type="HTTPStatusError",
                    error_code="STORAGE_005",
                    upstream_service="nhn_storage_iam",
                    http_status=e.response.status_code if hasattr(e, 'response') else None,
                    event="storage",
                    exc_info=True,
                )
                raise Exception("IAM 인증에 실패했습니다.")
            except httpx.HTTPError as e:
                log_error(
                    "Storage authentication network error",
                    error_type="NetworkError",
                    error_code="STORAGE_006",
                    upstream_service="nhn_storage_iam",
                    event="storage",
                    exc_info=True,
                )
                raise Exception("IAM 인증 중 네트워크 오류가 발생했습니다.")
            except Exception as e:
                error_msg = str(e)
                if "IAM" in error_msg or "네트워크" in error_msg:
                    raise
                log_error(
                    "Storage authentication failed with unexpected error",
                    error_type=type(e).__name__,
                    error_message=error_msg,
                    error_code="STORAGE_007",
                    upstream_service="nhn_storage_iam",
                    event="storage",
                    exc_info=True,
                )
                raise Exception(f"Storage authentication failed: {error_msg}")
    
    def _get_storage_url(self) -> str:
        """
        Get the storage URL.
        API 문서: 스토리지 계정(Account)은 URL 경로에 포함
        형식: https://{region}-api-object-storage.nhncloudservice.com/v1/{account}
        """
        if self._storage_url:
            return self._storage_url
        # Fallback: 기본 URL 사용
        account = self._account or f"AUTH_{self.settings.nhn_storage_tenant_id}"
        return f"{self.settings.nhn_storage_url}/{account}"
    
    async def _ensure_container_exists(self, container_name: str) -> None:
        """
        Ensure container exists, create if it doesn't.
        API 문서: 컨테이너 생성은 PUT 메서드 사용
        
        Args:
            container_name: Name of the container to check/create
        """
        token = await self._get_auth_token()
        storage_url = self._get_storage_url()
        
        # 컨테이너 존재 확인 (HEAD 요청)
        url = f"{storage_url}/{container_name}"
        
        try:
            async with record_external_request("nhn_storage"):
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # HEAD 요청으로 컨테이너 존재 확인
                    response = await client.head(
                        url,
                        headers={"X-Auth-Token": token},
                    )

                    if response.status_code == 404:
                        create_response = await client.put(
                            url,
                            headers={"X-Auth-Token": token},
                        )
                        if create_response.status_code not in (201, 202):
                            logger.error(
                                "Container create failed",
                                extra={"event": "storage", "container": container_name, "status": create_response.status_code},
                            )
                    elif response.status_code not in (200, 204):
                        logger.error(
                            "Container check failed",
                            extra={"event": "storage", "container": container_name, "status": response.status_code},
                        )

        except Exception as e:
            logger.error("Container ensure failed", exc_info=e, extra={"event": "storage", "container": container_name})
    
    async def upload_file(
        self,
        file_content: bytes,
        object_name: str,
        content_type: str,
    ) -> str:
        """
        Upload a file to Object Storage.
        
        API 문서 참조: 오브젝트 업로드
        https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/api-guide/#_15
        
        Args:
            file_content: The file content as bytes
            object_name: The name/path of the object in storage (예: photos/1/abc123.jpg)
            content_type: MIME type of the file
            
        Returns:
            The storage path of the uploaded file (container/object_name)
        """
        token = await self._get_auth_token()
        storage_url = self._get_storage_url()
        container = self.settings.nhn_storage_container
        
        # 컨테이너가 존재하는지 확인하고 없으면 생성
        await self._ensure_container_exists(container)
        
        # API 문서 형식: {storage_url}/{container}/{object}
        url = f"{storage_url}/{container}/{object_name}"
        
        try:
            async with record_external_request("nhn_storage"):
                async with httpx.AsyncClient(timeout=60.0) as client:
                    # PUT 메서드로 오브젝트 업로드
                    response = await client.put(
                        url,
                        content=file_content,
                        headers={
                            "X-Auth-Token": token,
                            "Content-Type": content_type,
                        },
                    )

                    if response.status_code not in (200, 201):
                        logger.error(
                            "File upload failed",
                            extra={"event": "storage", "status": response.status_code, "object": object_name},
                        )
                        raise Exception("File upload failed")

                    # 반환 형식: container/object_name (업로드 성공은 로깅 안 함)
                    return f"{container}/{object_name}"

        except httpx.TimeoutException:
            logger.error("File upload timeout", extra={"event": "storage", "object": object_name})
            raise Exception("File upload timeout")
        except httpx.HTTPError as e:
            logger.error("File upload HTTP error", exc_info=e, extra={"event": "storage", "object": object_name})
            raise Exception("File upload failed")
        except Exception as e:
            if "File upload" in str(e):
                raise
            logger.error("File upload failed", exc_info=e, extra={"event": "storage", "object": object_name})
            raise Exception("File upload failed")
    
    async def download_file(self, object_name: str) -> bytes:
        """
        Download a file from Object Storage.
        
        API 문서 참조: 오브젝트 다운로드
        https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/api-guide/#_18
        
        Args:
            object_name: The name/path of the object in storage (예: image/1/abc123.jpg)
                        컨테이너는 포함하지 않음
            
        Returns:
            The file content as bytes
        """
        token = await self._get_auth_token()
        storage_url = self._get_storage_url()
        container = self.settings.nhn_storage_container
        
        # object_name이 이미 container/object 형식인지 확인
        # 예: "photo-container/image/1/abc.jpg" vs "image/1/abc.jpg"
        if object_name.startswith(f"{container}/"):
            # 이미 컨테이너가 포함된 경우
            url = f"{storage_url}/{object_name}"
        else:
            url = f"{storage_url}/{container}/{object_name}"
        
        try:
            async with record_external_request("nhn_storage"):
                async with httpx.AsyncClient(timeout=60.0) as client:
                    # GET 메서드로 오브젝트 다운로드
                    response = await client.get(
                        url,
                        headers={"X-Auth-Token": token},
                    )

                    if response.status_code != 200:
                        logger.error(
                            "File download failed",
                            extra={"event": "storage", "status": response.status_code, "object": object_name},
                        )
                        raise Exception(f"File download failed: HTTP {response.status_code}")
                    return response.content

        except httpx.TimeoutException:
            logger.error("File download timeout", extra={"event": "storage", "object": object_name})
            raise Exception("File download timeout")
        except httpx.HTTPError as e:
            logger.error("File download HTTP error", exc_info=e, extra={"event": "storage", "object": object_name})
            raise Exception(f"File download failed: {str(e)}")
        except Exception as e:
            if "File download" in str(e):
                raise
            logger.error("File download failed", exc_info=e, extra={"event": "storage", "object": object_name})
            raise
    
    async def delete_file(self, object_name: str) -> bool:
        """
        Delete a file from Object Storage.
        
        API 문서 참조: 오브젝트 삭제
        https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/api-guide/#_19
        
        Args:
            object_name: The name/path of the object in storage (container/object 형식)
            
        Returns:
            True if deletion was successful
        """
        token = await self._get_auth_token()
        storage_url = self._get_storage_url()
        
        # object_name이 container/object 형식인지 확인
        if "/" in object_name:
            url = f"{storage_url}/{object_name}"
        else:
            container = self.settings.nhn_storage_container
            url = f"{storage_url}/{container}/{object_name}"
        
        try:
            async with record_external_request("nhn_storage"):
                async with httpx.AsyncClient(timeout=30.0) as client:
                    # DELETE 메서드로 오브젝트 삭제
                    response = await client.delete(
                        url,
                        headers={"X-Auth-Token": token},
                    )

                    success = response.status_code in (204, 404)
                    if not success:
                        logger.error(
                            "File deletion failed",
                            extra={"event": "storage", "status": response.status_code, "object": object_name},
                        )
                    return success

        except httpx.TimeoutException:
            logger.error("File deletion timeout", extra={"event": "storage", "object": object_name})
            return False
        except httpx.HTTPError as e:
            logger.error("File deletion failed", exc_info=e, extra={"event": "storage", "object": object_name})
            return False
        except Exception as e:
            logger.error("File deletion failed", exc_info=e, extra={"event": "storage", "object": object_name})
            return False
    
    async def file_exists(self, object_name: str) -> bool:
        """
        Check if a file exists in Object Storage.
        
        API 문서: 오브젝트 정보 조회 (HEAD 메서드)
        https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/api-guide/#_17
        
        Args:
            object_name: The name/path of the object in storage (container/object 형식)
            
        Returns:
            True if the file exists
        """
        token = await self._get_auth_token()
        storage_url = self._get_storage_url()
        
        # object_name이 container/object 형식인지 확인
        if "/" in object_name:
            url = f"{storage_url}/{object_name}"
        else:
            container = self.settings.nhn_storage_container
            url = f"{storage_url}/{container}/{object_name}"
        
        try:
            async with record_external_request("nhn_storage"):
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # HEAD 메서드로 오브젝트 정보 조회
                    response = await client.head(
                        url,
                        headers={"X-Auth-Token": token},
                    )

                    # 200 OK면 존재함
                    return response.status_code == 200

        except Exception as e:
            logger.error("File exists check failed", exc_info=e, extra={"event": "storage", "object": object_name})
            return False
    
    def _get_s3_client(self) -> boto3.client:
        """
        Get or create S3 client for presigned URL generation.
        
        NHN Cloud S3 API 참조:
        https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/s3-api-guide/
        
        Returns:
            Configured boto3 S3 client
        """
        if self._s3_client is not None:
            return self._s3_client
        
        if not self.settings.nhn_s3_access_key or not self.settings.nhn_s3_secret_key:
            raise Exception(
                "S3 API credentials not configured. "
                "Please set NHN_S3_ACCESS_KEY and NHN_S3_SECRET_KEY environment variables."
            )
        
        # S3 API 엔드포인트는 호스트만 사용. /v1/AUTH_xxx 같은 경로가 있으면 서버가 'v1'을 버킷으로 잘못 해석함(InvalidBucketName).
        endpoint = (self.settings.nhn_s3_endpoint_url or "").strip()
        if endpoint:
            from urllib.parse import urlparse
            parsed = urlparse(endpoint if "://" in endpoint else f"https://{endpoint}")
            endpoint = f"{parsed.scheme or 'https'}://{parsed.netloc or parsed.path.split('/')[0]}"
        
        # NHN Cloud S3 API 설정
        # 참조: https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/s3-api-guide/#aws-sdk
        self._s3_client = boto3.client(
            's3',
            aws_access_key_id=self.settings.nhn_s3_access_key,
            aws_secret_access_key=self.settings.nhn_s3_secret_key,
            endpoint_url=endpoint or self.settings.nhn_s3_endpoint_url,
            region_name=self.settings.nhn_s3_region_name,
            config=Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'}  # NHN Cloud는 path-style URL 사용
            )
        )
        
        return self._s3_client
    
    def generate_presigned_upload_url(
        self,
        object_name: str,
        content_type: str,
        expires_in: Optional[int] = None,
    ) -> Dict[str, str]:
        """
        Generate a presigned URL for direct upload to Object Storage.
        
        NHN Cloud S3 API 참조:
        https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/s3-api-guide/
        
        Args:
            object_name: The name/path of the object in storage (예: photos/1/abc123.jpg)
            content_type: MIME type of the file
            expires_in: URL expiration time in seconds (default: from settings)
            
        Returns:
            Dictionary with 'url' and 'fields' for the upload
            
        Example:
            >>> service = get_storage_service()
            >>> result = service.generate_presigned_upload_url(
            ...     "photos/1/test.jpg",
            ...     "image/jpeg",
            ...     expires_in=3600
            ... )
            >>> print(result['url'])  # Use this URL for PUT request
        """
        if expires_in is None:
            expires_in = self.settings.nhn_s3_presigned_url_expire_seconds
        
        container = self.settings.nhn_storage_container
        s3_client = self._get_s3_client()
        
        try:
            # Presigned URL for PUT only. 이미지 보기는 S3 GET presigned 미사용 (CDN Auth Token 또는 백엔드 스트리밍).
            url = s3_client.generate_presigned_url(
                ClientMethod='put_object',
                Params={
                    'Bucket': container,
                    'Key': object_name,
                    'ContentType': content_type,
                },
                ExpiresIn=expires_in,
                HttpMethod='PUT'
            )
            
            return {
                'url': url,
                'method': 'PUT',
                'headers': {
                    'Content-Type': content_type,
                }
            }
            
        except ClientError as e:
            logger.error(
                "Presigned URL generation failed",
                exc_info=e,
                extra={"event": "storage", "object": object_name}
            )
            raise Exception(f"Failed to generate presigned URL: {str(e)}")
        except Exception as e:
            logger.error(
                "Presigned URL generation failed",
                exc_info=e,
                extra={"event": "storage", "object": object_name}
            )
            raise Exception(f"Failed to generate presigned URL: {str(e)}")


# Singleton instance
_storage_service: Optional[NHNObjectStorageService] = None


def get_storage_service() -> NHNObjectStorageService:
    """Get the singleton storage service instance."""
    global _storage_service
    if _storage_service is None:
        _storage_service = NHNObjectStorageService()
    return _storage_service
