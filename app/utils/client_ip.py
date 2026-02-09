"""
클라이언트 IP 추출 유틸리티.

프록시나 로드밸런서를 거치는 경우 실제 클라이언트 IP를 추출합니다.
"""
from typing import Optional
from fastapi import Request


def get_client_ip(request: Request) -> Optional[str]:
    """
    요청에서 실제 클라이언트 IP를 추출합니다.
    
    프록시 환경에서 다음 헤더를 순서대로 확인합니다:
    1. X-Forwarded-For (가장 일반적, 쉼표로 구분된 IP 리스트)
    2. X-Real-IP (nginx 등에서 설정)
    3. CF-Connecting-IP (Cloudflare)
    4. True-Client-IP (Akamai, Cloudflare Enterprise)
    5. request.client.host (직접 연결)
    
    Args:
        request: FastAPI Request 객체
        
    Returns:
        클라이언트 IP 주소 (문자열) 또는 None
        
    Note:
        X-Forwarded-For 형식: "client, proxy1, proxy2"
        첫 번째 IP가 실제 클라이언트 IP입니다.
        
    Security:
        프로덕션 환경에서는 신뢰할 수 있는 프록시에서만 이 헤더들을 허용해야 합니다.
        악의적인 클라이언트가 이 헤더를 위조할 수 있으므로, 로드밸런서/프록시 설정에서
        외부 요청의 이 헤더들을 제거하고, 내부에서만 설정하도록 해야 합니다.
    """
    # 1. X-Forwarded-For 확인 (가장 일반적)
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        # 쉼표로 구분된 IP 리스트에서 첫 번째 (실제 클라이언트) IP 추출
        client_ip = x_forwarded_for.split(",")[0].strip()
        if client_ip:
            return client_ip
    
    # 2. X-Real-IP 확인 (nginx 등)
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip.strip()
    
    # 3. CF-Connecting-IP 확인 (Cloudflare)
    cf_connecting_ip = request.headers.get("CF-Connecting-IP")
    if cf_connecting_ip:
        return cf_connecting_ip.strip()
    
    # 4. True-Client-IP 확인 (Akamai, Cloudflare Enterprise)
    true_client_ip = request.headers.get("True-Client-IP")
    if true_client_ip:
        return true_client_ip.strip()
    
    # 5. 직접 연결 (프록시 없음)
    if request.client:
        return request.client.host
    
    return None


def get_forwarded_proto(request: Request) -> str:
    """
    요청의 원본 프로토콜을 추출합니다 (http 또는 https).
    
    프록시 환경에서는 X-Forwarded-Proto 헤더를 확인합니다.
    
    Args:
        request: FastAPI Request 객체
        
    Returns:
        프로토콜 (http 또는 https)
    """
    # X-Forwarded-Proto 확인
    x_forwarded_proto = request.headers.get("X-Forwarded-Proto")
    if x_forwarded_proto:
        return x_forwarded_proto.lower()
    
    # URL 스키마 확인
    return request.url.scheme


def get_forwarded_host(request: Request) -> str:
    """
    요청의 원본 호스트를 추출합니다.
    
    프록시 환경에서는 X-Forwarded-Host 헤더를 확인합니다.
    
    Args:
        request: FastAPI Request 객체
        
    Returns:
        호스트명
    """
    # X-Forwarded-Host 확인
    x_forwarded_host = request.headers.get("X-Forwarded-Host")
    if x_forwarded_host:
        return x_forwarded_host
    
    # Host 헤더 확인
    return request.headers.get("Host", "")
