#!/usr/bin/env python3
"""
NHN Cloud 리소스 정리: 빌드/테스트 인스턴스 삭제, Floating IP 해제, 키페어 삭제.
환경 변수: TOKEN, COMPUTE_URL,
  BUILD_INSTANCE_ID(선택), TEST_INSTANCE_ID(선택),
  BUILD_FLOATING_IP_ID(선택), TEST_FLOATING_IP_ID(선택), KEYPAIR_NAME(선택)
값이 비어 있으면 해당 리소스는 건너뜀.
"""
import os
import requests

from nhn_api import release_floating_ip


def main() -> None:
    token = os.environ["TOKEN"]
    compute_url = os.environ["COMPUTE_URL"]
    build_instance_id = os.environ.get("BUILD_INSTANCE_ID", "").strip()
    test_instance_id = os.environ.get("TEST_INSTANCE_ID", "").strip()
    build_floating_ip_id = os.environ.get("BUILD_FLOATING_IP_ID", "").strip()
    test_floating_ip_id = os.environ.get("TEST_FLOATING_IP_ID", "").strip()
    keypair_name = os.environ.get("KEYPAIR_NAME", "").strip()
    headers = {
        "X-Auth-Token": token,
        "Content-Type": "application/json",
    }

    if build_instance_id:
        try:
            print(f"🗑️  빌드 인스턴스 삭제 중: {build_instance_id}")
            requests.delete(
                f"{compute_url}/servers/{build_instance_id}",
                headers=headers,
            )
            print("✅ 빌드 인스턴스 삭제 요청 완료")
        except Exception as e:
            print(f"⚠️  빌드 인스턴스 삭제 실패: {e}")

    if test_instance_id:
        try:
            print(f"🗑️  테스트 인스턴스 삭제 중: {test_instance_id}")
            requests.delete(
                f"{compute_url}/servers/{test_instance_id}",
                headers=headers,
            )
            print("✅ 테스트 인스턴스 삭제 요청 완료")
        except Exception as e:
            print(f"⚠️  테스트 인스턴스 삭제 실패: {e}")

    for name, fip_id in [("빌드", build_floating_ip_id), ("테스트", test_floating_ip_id)]:
        if fip_id:
            try:
                print(f"🌐 {name} Floating IP 해제 중: {fip_id}")
                release_floating_ip(compute_url, headers, fip_id)
                print(f"✅ {name} Floating IP 해제 완료")
            except Exception as e:
                print(f"⚠️  {name} Floating IP 해제 실패: {e}")

    if keypair_name:
        try:
            print(f"🔑 키페어 삭제 중: {keypair_name}")
            requests.delete(
                f"{compute_url}/os-keypairs/{keypair_name}",
                headers=headers,
            )
            print("✅ 키페어 삭제 완료")
        except Exception as e:
            print(f"⚠️  키페어 삭제 실패: {e}")

    print("✅ 리소스 정리 완료")


if __name__ == "__main__":
    main()
