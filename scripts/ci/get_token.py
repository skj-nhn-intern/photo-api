#!/usr/bin/env python3
"""
NHN Cloud 토큰 발급. Cleanup job 등에서 재인증용.
환경 변수: NHN_AUTH_URL, NHN_TENANT_ID, NHN_USERNAME, NHN_PASSWORD, NHN_REGION
GITHUB_OUTPUT에 token, compute_url 기록.
"""
import os

from nhn_api import get_token_and_compute_url


def main() -> None:
    auth_url = os.environ["NHN_AUTH_URL"]
    tenant_id = os.environ["NHN_TENANT_ID"]
    username = os.environ["NHN_USERNAME"]
    password = os.environ["NHN_PASSWORD"]
    region = os.environ.get("NHN_REGION", "KR1")
    token, compute_url, _ = get_token_and_compute_url(
        auth_url, tenant_id, username, password, region
    )
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"token={token}\n")
            f.write(f"compute_url={compute_url}\n")
    print("✅ 토큰 발급 완료")


if __name__ == "__main__":
    main()
