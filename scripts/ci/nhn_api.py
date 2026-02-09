"""
NHN Cloud Compute API 공통 모듈.
GitHub Actions 인스턴스 이미지 빌드에서 사용.
"""
import re
import sys
from typing import Optional

import requests


# OpenStack Nova 스타일 Floating IP (NHN Cloud 등)
_DEFAULT_FLOATING_IP_POOLS = ("public", "Public", "ext_net", "external")


def _allocate_floating_ip_with_pool(
    compute_url: str, headers: dict, pool: str
) -> tuple[str, str]:
    """지정한 풀에서 Floating IP 하나 할당. 반환: (ip_address, floating_ip_id)."""
    r = requests.post(
        f"{compute_url}/os-floating-ips",
        headers=headers,
        json={"pool": pool},
    )
    r.raise_for_status()
    data = r.json()
    fip = data.get("floating_ip") or data
    ip_addr = fip.get("ip") or fip.get("floating_ip_address")
    fip_id = fip.get("id")
    if not ip_addr or not fip_id:
        raise ValueError(f"Floating IP 응답 형식 예상 외: {data}")
    return ip_addr, fip_id


def allocate_floating_ip(
    compute_url: str, headers: dict, pool: Optional[str] = None
) -> tuple[str, str]:
    """풀에서 Floating IP 하나 할당. pool이 비어 있으면 사용 가능한 풀을 자동 선택.
    반환: (ip_address, floating_ip_id)."""
    pool = (pool or "").strip()
    if pool:
        return _allocate_floating_ip_with_pool(compute_url, headers, pool)
    # 풀 목록 조회 시도 (Nova os-floating-ip-pools)
    try:
        r = requests.get(f"{compute_url}/os-floating-ip-pools", headers=headers)
        if r.ok:
            data = r.json()
            pools = data.get("floating_ip_pools") or data.get("pools") or []
            names = [p.get("name") for p in pools if isinstance(p, dict) and p.get("name")]
            if names:
                return _allocate_floating_ip_with_pool(compute_url, headers, names[0])
    except Exception:
        pass
    # 기본 풀 이름 순서대로 시도
    for candidate in _DEFAULT_FLOATING_IP_POOLS:
        try:
            return _allocate_floating_ip_with_pool(compute_url, headers, candidate)
        except requests.exceptions.HTTPError:
            continue
    raise RuntimeError(
        "Floating IP 할당 실패. NHN_FLOATING_IP_POOL에 풀 이름을 지정하거나, 콘솔에서 사용 가능한 풀을 확인하세요."
    )


def add_floating_ip_to_server(
    compute_url: str, headers: dict, server_id: str, floating_ip_address: str
) -> None:
    """인스턴스에 Floating IP 연결 (Nova addFloatingIp)."""
    r = requests.post(
        f"{compute_url}/servers/{server_id}/action",
        headers=headers,
        json={"addFloatingIp": {"address": floating_ip_address}},
    )
    r.raise_for_status()


def release_floating_ip(compute_url: str, headers: dict, floating_ip_id: str) -> None:
    """Floating IP 해제(반환)."""
    r = requests.delete(
        f"{compute_url}/os-floating-ips/{floating_ip_id}",
        headers=headers,
    )
    if r.status_code == 404:
        return  # 이미 삭제됨
    r.raise_for_status()

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _is_uuid(value: str) -> bool:
    return bool(value and _UUID_RE.match(value.strip()))


def get_token_and_compute_url(
    auth_url: str,
    tenant_id: str,
    username: str,
    password: str,
    region: str,
) -> tuple[str, str, Optional[str]]:
    """토큰 발급 후 Compute API URL 및 Volume(Block Storage) URL 반환. volume_url은 없을 수 있음."""
    auth_payload = {
        "auth": {
            "tenantId": tenant_id,
            "passwordCredentials": {
                "username": username,
                "password": password,
            },
        }
    }
    auth_response = requests.post(f"{auth_url.rstrip('/')}/tokens", json=auth_payload)
    auth_response.raise_for_status()
    data = auth_response.json()
    token = data["access"]["token"]["id"]
    compute_url = None
    volume_url = None
    for service in data["access"].get("serviceCatalog", []):
        stype = service.get("type") or ""
        for endpoint in service.get("endpoints", []):
            if endpoint.get("region") != region:
                continue
            url = endpoint.get("publicURL")
            if stype == "compute":
                compute_url = url
            elif stype in ("volume", "volumev3"):
                volume_url = url
    if not compute_url:
        print(f"❌ Compute endpoint not found for region: {region}", file=sys.stderr)
        sys.exit(1)
    return token, compute_url, volume_url


def get_headers(token: str) -> dict:
    return {
        "X-Auth-Token": token,
        "Content-Type": "application/json",
    }


def get_server_ip(server_data: dict) -> Optional[str]:
    """server 상세 응답에서 IPv4 주소 추출."""
    for addresses in server_data.get("addresses", {}).values():
        for addr in addresses:
            if addr.get("version") == 4:
                return addr.get("addr")
    return None


def resolve_flavor_uuid(compute_url: str, headers: dict, flavor_ref: str) -> str:
    """flavor_ref가 UUID면 그대로, 아니면 이름으로 조회해 UUID 반환."""
    if _is_uuid(flavor_ref):
        return flavor_ref.strip()
    r = requests.get(f"{compute_url}/flavors/detail", headers=headers)
    r.raise_for_status()
    name_lower = flavor_ref.strip().lower()
    for f in r.json().get("flavors", []):
        if f.get("name", "").lower() == name_lower:
            return f["id"]
    for f in r.json().get("flavors", []):
        if name_lower in f.get("name", "").lower():
            return f["id"]
    print(f"❌ Flavor를 찾을 수 없음: {flavor_ref}", file=sys.stderr)
    sys.exit(1)


def resolve_image_uuid(region: str, token: str, image_ref: str) -> str:
    """image_ref가 UUID면 그대로, 아니면 이름으로 Public 이미지 조회해 UUID 반환.
    동일 이름이 여러 개면 created_at 최신 순으로 하나 선택."""
    if _is_uuid(image_ref):
        return image_ref.strip()
    region_lower = region.strip().lower()
    image_url = f"https://{region_lower}-api-image-infrastructure.nhncloudservice.com"
    headers = {"X-Auth-Token": token}
    r = requests.get(
        f"{image_url}/v2/images",
        headers=headers,
        params={"visibility": "public", "limit": 100},
    )
    r.raise_for_status()
    body = r.json()
    images = body.get("images") or []
    name_lower = image_ref.strip().lower()
    exact = [img for img in images if (img.get("name") or "").lower() == name_lower]
    if exact:
        candidates = exact
    else:
        candidates = [
            img for img in images
            if name_lower in (img.get("name") or "").lower()
        ]
    if not candidates:
        print(f"❌ 이미지를 찾을 수 없음: {image_ref}", file=sys.stderr)
        sys.exit(1)
    # 여러 개면 created_at 최신 순 (없으면 맨 뒤)
    candidates.sort(key=lambda img: img.get("created_at") or "", reverse=True)
    chosen = candidates[0]
    if len(candidates) > 1:
        print(f"ℹ️  이미지 이름 '{image_ref}' 후보 {len(candidates)}개 중 최신 사용: {chosen['id']} (created_at={chosen.get('created_at', '?')})")
    return chosen["id"]
