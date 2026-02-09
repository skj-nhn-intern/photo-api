# CI 스크립트 (NHN Cloud 인스턴스 이미지 빌드)

GitHub Actions 워크플로우 `build-and-test-image.yml`에서 사용하는 NHN Cloud Compute API 스크립트입니다.  
인라인 Python을 파일로 분리해 유지보수·재사용·테스트를 쉽게 합니다.

## 파일 구성

| 파일 | 역할 | 입력 (환경 변수) | 출력 |
|------|------|------------------|------|
| `nhn_api.py` | 공통 모듈 (인증, 헤더, IP 추출) | — | — |
| `create_build_instance.py` | 빌드용 인스턴스 생성, ACTIVE 대기 | NHN_* secrets, SSH_PUBLIC_KEY | GITHUB_OUTPUT: instance_id, instance_ip, keypair_name, token, compute_url |
| `stop_instance.py` | 인스턴스 중지, SHUTOFF 대기 | TOKEN, COMPUTE_URL, INSTANCE_ID | — |
| `create_image.py` | 인스턴스 → 이미지 생성, active 대기 | TOKEN, COMPUTE_URL, INSTANCE_ID, GIT_SHA | GITHUB_OUTPUT: image_id, image_name |
| `copy_image_to_region.py` | KR1 이미지를 KR2 Image API로 복사 (인스턴스 생성 없음) | TOKEN, COMPUTE_URL 또는 SOURCE_IMAGE_BASE_URL, SOURCE_IMAGE_ID, SOURCE_IMAGE_NAME, TARGET_REGION, TARGET_IMAGE_BASE_URL(시크릿 권장) | GITHUB_OUTPUT: target_image_id, target_region |
| `create_test_instance.py` | 테스트 인스턴스 생성, ACTIVE 대기 | TOKEN, COMPUTE_URL, IMAGE_ID, NHN_NETWORK_ID, NHN_FLAVOR_NAME, KEYPAIR_NAME 등 | GITHUB_OUTPUT: test_instance_id, test_instance_ip |
| `cleanup.py` | 인스턴스·키페어 삭제 | TOKEN, COMPUTE_URL, BUILD_INSTANCE_ID, TEST_INSTANCE_ID, KEYPAIR_NAME | — |

## 로컬에서 실행 (테스트용)

필요한 환경 변수를 설정한 뒤, **저장소 루트**에서 실행하세요.

```bash
# 저장소 루트에서
export NHN_AUTH_URL="..."
export NHN_TENANT_ID="..."
# ... 나머지 secrets
export SSH_PUBLIC_KEY="$(cat /path/to/key.pub)"

python3 scripts/ci/create_build_instance.py
```

`nhn_api` 임포트는 스크립트가 위치한 `scripts/ci/` 디렉토리를 기준으로 동작합니다.

## 의존성

- Python 3.10+
- `requests` (워크플로우에서 `pip install requests`로 설치)
