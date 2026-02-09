#!/usr/bin/env python3
"""
NHN Cloud 인스턴스를 중지하고 SHUTOFF 될 때까지 대기.
환경 변수: TOKEN, COMPUTE_URL, INSTANCE_ID
"""
import os
import sys
import time

import requests


def main() -> None:
    token = os.environ["TOKEN"]
    compute_url = os.environ["COMPUTE_URL"]
    server_id = os.environ["INSTANCE_ID"]
    headers = {
        "X-Auth-Token": token,
        "Content-Type": "application/json",
    }

    print("⏹️  인스턴스 중지 요청 중...")
    r = requests.post(
        f"{compute_url}/servers/{server_id}/action",
        headers=headers,
        json={"os-stop": None},
    )
    r.raise_for_status()

    print("⏳ 인스턴스가 SHUTOFF 상태가 될 때까지 대기 중...")
    max_wait = 300
    start = time.time()
    while time.time() - start < max_wait:
        detail = requests.get(
            f"{compute_url}/servers/{server_id}",
            headers=headers,
        )
        detail.raise_for_status()
        status = detail.json()["server"]["status"]
        if status == "SHUTOFF":
            print("✅ 인스턴스 중지 완료")
            return
        print(f"  상태: {status}, 대기 중...")
        time.sleep(5)

    print("❌ 타임아웃: 인스턴스가 중지되지 않았습니다", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
