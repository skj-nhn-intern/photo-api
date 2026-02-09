#!/usr/bin/env python3
"""
생성된 이미지로 테스트 인스턴스를 띄우고 ACTIVE 될 때까지 대기.
환경 변수: TOKEN, COMPUTE_URL, IMAGE_ID, NHN_NETWORK_ID, NHN_FLAVOR_NAME,
  NHN_SECURITY_GROUP_ID(선택), KEYPAIR_NAME
GITHUB_OUTPUT에 test_instance_id, test_instance_ip 기록.
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
    resolve_flavor_uuid,
)


def main() -> None:
    token = os.environ["TOKEN"]
    compute_url = os.environ["COMPUTE_URL"]
    image_id = os.environ["IMAGE_ID"]
    network_id = os.environ["NHN_NETWORK_ID"]
    flavor_id = os.environ["NHN_FLAVOR_NAME"]
    keypair_name = os.environ["KEYPAIR_NAME"]
    security_group_id = os.environ.get("NHN_SECURITY_GROUP_ID", "")
    floating_ip_pool = os.environ.get("NHN_FLOATING_IP_POOL", "").strip()
    headers = get_headers(token)

    # Flavor는 이름(u2.c2m4 등)으로 넣어도 UUID로 자동 조회
    flavor_id = resolve_flavor_uuid(compute_url, headers, flavor_id)

    root_volume_size = int(os.environ.get("NHN_ROOT_VOLUME_SIZE_GB", "20"))
    instance_name = f"photo-api-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    # NHN: networks는 서브넷 ID일 때 "subnet" 키 사용
    server_payload = {
        "server": {
            "name": instance_name,
            "imageRef": image_id,
            "flavorRef": flavor_id,
            "networks": [{"subnet": network_id}],
            "key_name": keypair_name,
            "min_count": 1,
            "max_count": 1,
            "metadata": {"purpose": "github-actions-test", "app": "photo-api"},
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
    test_server_id = r.json()["server"]["id"]
    print(f"⏳ 테스트 인스턴스 ACTIVE 대기 중: {test_server_id}")

    max_wait = 600
    start = time.time()
    while time.time() - start < max_wait:
        detail = requests.get(
            f"{compute_url}/servers/{test_server_id}",
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
            test_floating_ip_id = ""
            try:
                float_ip, test_floating_ip_id = allocate_floating_ip(
                    compute_url, headers, floating_ip_pool or None
                )
                add_floating_ip_to_server(
                    compute_url, headers, test_server_id, float_ip
                )
                ip_address = float_ip
                print(f"✅ 테스트 인스턴스 ACTIVE: Floating IP={ip_address}")
            except Exception as e:
                print(f"⚠️  Floating IP 할당/연결 실패: {e}", file=sys.stderr)
                print(f"✅ 테스트 인스턴스 ACTIVE: {ip_address}")
            out = os.environ.get("GITHUB_OUTPUT")
            if out:
                with open(out, "a") as f:
                    f.write(f"test_instance_id={test_server_id}\n")
                    f.write(f"test_instance_ip={ip_address}\n")
                    if test_floating_ip_id:
                        f.write(f"test_floating_ip_id={test_floating_ip_id}\n")
            return
        if status == "ERROR":
            print("❌ 테스트 인스턴스 생성 실패", file=sys.stderr)
            sys.exit(1)
        print(f"  상태: {status}, 대기 중...")
        time.sleep(10)

    print("❌ 타임아웃: 테스트 인스턴스가 시작되지 않았습니다", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
