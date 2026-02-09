#!/usr/bin/env python3
"""
NHN Cloud에 빌드용 인스턴스를 생성하고 ACTIVE 될 때까지 대기.
환경 변수로 입력받고, GITHUB_OUTPUT에 결과를 쓴다.
"""
import os
import sys
import time
from datetime import datetime

import requests

from nhn_api import (
    add_floating_ip_to_server,
    allocate_floating_ip,
    get_headers,
    get_server_ip,
    get_token_and_compute_url,
    resolve_flavor_uuid,
    resolve_image_uuid,
)


def main() -> None:
    auth_url = os.environ["NHN_AUTH_URL"]
    tenant_id = os.environ["NHN_TENANT_ID"]
    username = os.environ["NHN_USERNAME"]
    password = os.environ["NHN_PASSWORD"]
    region = os.environ["NHN_REGION"]
    flavor_id = os.environ["NHN_FLAVOR_NAME"]
    image_id = os.environ["NHN_IMAGE_NAME"]
    network_id = os.environ["NHN_NETWORK_ID"]
    security_group_id = os.environ.get("NHN_SECURITY_GROUP_ID", "")
    floating_ip_pool = os.environ.get("NHN_FLOATING_IP_POOL", "").strip()
    ssh_public_key_path = os.environ["SSH_PUBLIC_KEY"]

    with open(ssh_public_key_path, "r") as f:
        ssh_public_key = f.read().strip()

    print("🔐 NHN Cloud 인증 중...")
    token, compute_url, volume_url = get_token_and_compute_url(
        auth_url, tenant_id, username, password, region
    )
    headers = get_headers(token)

    # 이름으로 넣은 경우 API에서 UUID로 조회 (Flavor / Image)
    flavor_id = resolve_flavor_uuid(compute_url, headers, flavor_id)
    image_id = resolve_image_uuid(region, token, image_id)

    keypair_name = f"github-actions-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    print(f"🔑 키페어 등록 중: {keypair_name}")
    keypair_payload = {
        "keypair": {"name": keypair_name, "public_key": ssh_public_key}
    }
    try:
        r = requests.post(
            f"{compute_url}/os-keypairs",
            headers=headers,
            json=keypair_payload,
        )
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"⚠️  키페어 등록 실패 (이미 존재할 수 있음): {e}")

    # 루트 디스크 크기(GB). Linux 최소 10, 문서 예시 20
    root_volume_size = int(os.environ.get("NHN_ROOT_VOLUME_SIZE_GB", "20"))
    instance_name = f"photo-api-build-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    print(f"🚀 빌드 인스턴스 생성 중: {instance_name}")
    # NHN Cloud API: block_device_mapping_v2 필수 (https://docs.nhncloud.com/ko/Compute/Instance/ko/public-api/)
    # networks: 서브넷 ID는 "subnet" 키 사용 (문서 예시 및 GITHUB_ACTIONS_SETUP.md 기준)
    server_payload = {
        "server": {
            "name": instance_name,
            "imageRef": image_id,
            "flavorRef": flavor_id,
            "networks": [{"subnet": network_id}],
            "key_name": keypair_name,
            "min_count": 1,
            "max_count": 1,
            "metadata": {"purpose": "github-actions-build", "app": "photo-api"},
            # NHN: destination_type 은 반드시 "volume". (local 이면 인스턴스 생성 400)
            "block_device_mapping_v2": [
                {
                    "source_type": "image",
                    "uuid": image_id,
                    "boot_index": 0,
                    "volume_size": root_volume_size,
                    "destination_type": "volume",
                    "delete_on_termination": True,
                }
            ],
        }
    }
    if security_group_id:
        server_payload["server"]["security_groups"] = [
            {"name": security_group_id}
        ]

    r = requests.post(f"{compute_url}/servers", headers=headers, json=server_payload)
    if not r.ok:
        print(f"❌ 인스턴스 생성 API 응답: {r.status_code}", file=sys.stderr)
        print(r.text[:500] if r.text else "(empty body)", file=sys.stderr)
    r.raise_for_status()
    server_id = r.json()["server"]["id"]
    print(f"✅ 인스턴스 생성 요청 완료: {server_id}")

    print("⏳ 인스턴스가 ACTIVE 상태가 될 때까지 대기 중...")
    max_wait = 600
    start = time.time()
    while time.time() - start < max_wait:
        detail = requests.get(
            f"{compute_url}/servers/{server_id}",
            headers=headers,
        )
        detail.raise_for_status()
        server_data = detail.json()["server"]
        status = server_data["status"]

        if status == "ACTIVE":
            ip_address = get_server_ip(server_data)
            if not ip_address:
                print("❌ IP 주소를 찾을 수 없습니다", file=sys.stderr)
                sys.exit(1)
            floating_ip_id = ""
            print("🌐 Floating IP 할당 중...")
            try:
                float_ip, floating_ip_id = allocate_floating_ip(
                    compute_url, headers, floating_ip_pool or None
                )
                add_floating_ip_to_server(
                    compute_url, headers, server_id, float_ip
                )
                ip_address = float_ip
                print(f"✅ 인스턴스 ACTIVE: Floating IP={ip_address}")
            except Exception as e:
                print(f"⚠️  Floating IP 할당/연결 실패: {e}", file=sys.stderr)
                print(f"   사설 IP로 진행: {ip_address}", file=sys.stderr)
            out = os.environ.get("GITHUB_OUTPUT")
            if out:
                with open(out, "a") as f:
                    f.write(f"instance_id={server_id}\n")
                    f.write(f"instance_ip={ip_address}\n")
                    f.write(f"instance_name={instance_name}\n")
                    f.write(f"keypair_name={keypair_name}\n")
                    f.write(f"token={token}\n")
                    f.write(f"compute_url={compute_url}\n")
                    if volume_url:
                        f.write(f"volume_url={volume_url}\n")
                    if floating_ip_id:
                        f.write(f"floating_ip_id={floating_ip_id}\n")
            return
        if status == "ERROR":
            print(f"❌ 인스턴스 생성 실패: {status}", file=sys.stderr)
            sys.exit(1)
        print(f"  상태: {status}, 대기 중...")
        time.sleep(10)

    print("❌ 타임아웃: 인스턴스가 ACTIVE 상태가 되지 않았습니다", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
