# GitHub Actions Setup Guide

이 문서는 NHN Cloud 인스턴스 이미지 빌드 및 테스트를 위한 GitHub Actions 워크플로우 설정 방법을 설명합니다.

## 개요

`build-and-test-image.yml` 워크플로우는 **한 job**에서 **이미지 만든 걸 KR1·KR2에 동일하게 업로드(create image)** 하고, **실제 실행 테스트는 KR1에서만** 수행합니다.

1. **KR1**: 빌드 인스턴스 → 빌드 → **create image (KR1)** → 테스트 인스턴스 생성 → **curl로 실행 테스트 (KR1만)**.
2. **KR2**: **이미지 업로드만.** KR1에서 만든 이미지를 KR2 Image API로 업로드 시도. 인스턴스 생성·빌드·테스트 없음. (NHN이 403이면 단계 실패, job은 continue-on-error로 성공.)
3. **리소스 정리**: KR1만. KR2에는 인스턴스를 만들지 않음.

**요약**: KR2 = 이미지 업로드만. 테스트·실행 테스트는 KR1만. Image API 참고: [Compute > Image > API 가이드](https://docs.nhncloud.com/ko/Compute/Image/ko/public-api/).

## 필수 GitHub Secrets 설정

GitHub 저장소 **Settings > Secrets and variables > Actions > Repository secrets**에서 아래 항목을 추가하세요.

### 체크리스트 (저장할 Secret 목록)

워크플로우가 실제로 참조하는 Secret만 나열했습니다. 비어 있으면 해당 단계가 실패할 수 있습니다.

| # | Secret 이름 | 용도 | 필수 |
|---|-------------|------|:----:|
| 1 | `NHN_AUTH_URL` | Identity API (토큰 발급) | ✅ |
| 2 | `NHN_TENANT_ID` | 테넌트/프로젝트 ID | ✅ |
| 3 | `NHN_USERNAME` | API 사용자(이메일 등) | ✅ |
| 4 | `NHN_PASSWORD` | API 비밀번호 | ✅ |
| 5 | `NHN_REGION` | 워크플로에서 KR1으로 고정 (Secret 불필요) | - |
| 6 | `NHN_FLAVOR_NAME` | 인스턴스 타입 이름 (빌드·테스트) | ✅ |
| 7 | `NHN_IMAGE_NAME` | 빌드용 베이스 이미지 이름 (Ubuntu 등) | ✅ |
| 8 | `NHN_NETWORK_ID` | KR1 VPC/서브넷 ID (공통으로 쓸 때) | ✅ |
| 8a | `NHN_NETWORK_ID_KR1` | KR1 전용 서브넷 ID (있으면 이 값 사용) | 선택 |
| 8b | `NHN_NETWORK_ID_KR2` | KR2 빌드 인스턴스용 서브넷 ID (있으면 이 값 사용) | 선택 |
| 9 | `NHN_FLOATING_IP_POOL` | Floating IP 풀 이름 (비우면 사용 가능한 풀 자동 선택) | 선택 |
| 10 | `NHN_SECURITY_GROUP_ID` | 보안 그룹 (SSH 22, 8000 허용) | ✅ |
| 11 | `LOKI_URL` | Promtail → Loki 주소 | ✅ |
| 12 | `DATABASE_URL` | DB 연결 문자열 (이미지 내 .env) | ✅ |
| 13 | `JWT_SECRET_KEY` | JWT 서명 키 (이미지 내 .env) | ✅ |
| 14 | `NHN_OBJECT_STORAGE_ENDPOINT` | Object Storage 엔드포인트 | ✅ |
| 15 | `NHN_OBJECT_STORAGE_ACCESS_KEY` | Object Storage Access Key | ✅ |
| 16 | `NHN_OBJECT_STORAGE_SECRET_KEY` | Object Storage Secret Key | ✅ |
| 17 | `NHN_CDN_DOMAIN` | CDN 도메인 (없으면 빈 값 가능) | 선택 |
| 18 | `NHN_CDN_AUTH_KEY` | CDN 인증 키 (없으면 빈 값 가능) | 선택 |
| 19 | `PROMETHEUS_PUSHGATEWAY_URL` | Pushgateway URL (커스텀 메트릭 푸시, 없으면 빈 값) | 선택 |
| 20 | `PROMETHEUS_PUSH_INTERVAL_SECONDS` | Pushgateway 푸시 주기(초, 기본 30) | 선택 |

**총 15~20개.** GitHub 호스트 러너는 VPC 밖이므로, 빌드/테스트 인스턴스에 **Floating IP**를 자동 할당합니다. 풀 이름을 지정하지 않으면 사용 가능한 풀을 자동으로 선택하며, 정리 시 IP를 해제합니다. CDN 미사용 시 16·17은 빈 문자열로 두거나 비워둬도 됩니다 (앱이 비어 있으면 미사용 처리하는 경우).

### 1. NHN Cloud 인증 정보

| Secret 이름 | 설명 | 예시 |
|-------------|------|------|
| `NHN_AUTH_URL` | NHN Cloud Identity API URL | `https://api-identity-infrastructure.nhncloudservice.com/v2.0` |
| `NHN_TENANT_ID` | 테넌트 ID (프로젝트 ID) | `a1b2c3d4e5f6...` |
| `NHN_USERNAME` | NHN Cloud API 사용자 이름 | `user@example.com` |
| `NHN_PASSWORD` | NHN Cloud API 비밀번호 | `your-password` |
| `NHN_REGION` | 리전 이름 | 워크플로에서 **KR1** 고정(빌드·검증·이미지 생성), 이미지는 KR2로 복사. Secret 불필요 |
| `NHN_IMAGE_BASE_URL_KR2` | KR2 Image API 베이스 URL (KR2 업로드용) | `https://kr2-api-image-infrastructure.nhncloudservice.com` | KR2 이미지 복사 시 필수. 미설정 시 리전으로 URL 추론 시도 |

### 2. NHN Cloud 인스턴스 설정

| Secret 이름 | 설명 | 예시 | 확인 방법 |
|-------------|------|------|----------|
| `NHN_FLAVOR_NAME` | 인스턴스 타입 **이름** | `u2.c2m4` | 스크립트가 API로 UUID 자동 조회 |
| `NHN_IMAGE_NAME` | **빌드용** 베이스 이미지 **이름** (동일 이름 여러 개면 전체 이름 사용) | `Ubuntu Server 22.04.5 LTS (2025.07.15)` | Public 이미지에서 이름 일치로 UUID 조회. 콘솔 2번째 컬럼(상세 이름)을 넣으면 원하는 것만 선택됨 |
| `NHN_NETWORK_ID` | **서브넷 ID** (UUID). KR1/KR2 공통이면 이것만 설정 | `b83863ff-0355-4c73-8c10-0bdf66a69aab` | Console > Network > VPC > 서브넷 상세에서 서브넷 ID 복사 |
| `NHN_NETWORK_ID_KR1` | KR1 전용 서브넷 ID (선택) | 리전별 VPC 사용 시 KR1 서브넷 UUID | 설정 시 KR1 job에서 이 값 사용 |
| `NHN_NETWORK_ID_KR2` | KR2 빌드 인스턴스용 서브넷 ID | KR2에서 동일 빌드 후 create image 시 사용 | 선택 |
| `NHN_FLOATING_IP_POOL` | Floating IP 풀 이름 (선택) | `public` 또는 비움 | 비우면 API로 풀 목록 조회 또는 기본값(public 등) 순서대로 시도해 자동 선택 |
| `NHN_SECURITY_GROUP_ID` | 보안 그룹 이름 또는 ID | `default` 또는 UUID | Console > Network > Security Group |

**Flavor / 이미지**: Secret에는 **이름**만 넣으면 됩니다. 스크립트가 API로 UUID를 조회해 사용합니다. 예: `NHN_FLAVOR_NAME` = `u2.c2m4`.  
**이미지**: `Ubuntu Server 22.04 LTS`처럼 짧게 넣으면 같은 이름이 여러 개일 수 있습니다. **순수 Ubuntu만 쓰려면** 콘솔에 보이는 상세 이름 전체를 넣으세요. 예: `NHN_IMAGE_NAME` = `Ubuntu Server 22.04.5 LTS (2025.07.15)` (NAT/Kafka/CUBRID 등 변형 제외). 사용 가능한 이름 목록을 확인하려면 로컬에서 아래를 실행하세요.

```bash
# 1) 환경 변수 설정 (실제 값으로 채우기)
export NHN_AUTH_URL="https://api-identity-infrastructure.nhncloudservice.com/v2.0"
export NHN_TENANT_ID="your-tenant-id"
export NHN_USERNAME="your-username"
export NHN_PASSWORD="your-password"
export NHN_REGION="KR1"   # KR1, KR2, JP1, US1 등

# 2) 토큰 발급
TOKEN=$(curl -s -X POST "${NHN_AUTH_URL}/tokens" \
  -H "Content-Type: application/json" \
  -d '{"auth":{"tenantId":"'"$NHN_TENANT_ID"'","passwordCredentials":{"username":"'"$NHN_USERNAME"'","password":"'"$NHN_PASSWORD'"'"}}"}' \
  | jq -r '.access.token.id')
if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then echo "토큰 발급 실패. NHN_AUTH_URL, TENANT_ID, USERNAME, PASSWORD 확인"; exit 1; fi

REGION_LOWER=$(echo "$NHN_REGION" | tr '[:upper:]' '[:lower:]')
COMPUTE_URL="https://${REGION_LOWER}-api-instance-infrastructure.nhncloudservice.com/v2/${NHN_TENANT_ID}"
IMAGE_URL="https://${REGION_LOWER}-api-image-infrastructure.nhncloudservice.com"

# 3) Flavor 목록 (name 컬럼을 NHN_FLAVOR_NAME 에 넣으면 됨)
echo "=== Flavor 목록 (NHN_FLAVOR_NAME 에 name 사용, 예: u2.c2m4) ==="
curl -s -H "X-Auth-Token: $TOKEN" "${COMPUTE_URL}/flavors/detail" \
  | jq -r '.flavors[] | "\(.name)  vCPU=\(.vcpus) RAM=\(.ram)MB"'

# 4) Ubuntu 이미지 목록 (name 컬럼을 NHN_IMAGE_NAME 에 넣으면 됨)
echo "=== Ubuntu 이미지 (NHN_IMAGE_NAME 에 name 사용, 예: Ubuntu 22.04) ==="
curl -s -H "X-Auth-Token: $TOKEN" \
  "${IMAGE_URL}/v2/images?visibility=public&limit=100" \
  | jq -r '.images[] | select(.name | test("Ubuntu"; "i")) | .name'
```

`jq`가 없으면 `brew install jq`(macOS) 또는 해당 OS 패키지 관리자로 설치하세요.

**테스트 인스턴스 이미지**: 테스트 인스턴스는 **빌드 인스턴스를 스냅샷한 이미지**로만 생성됩니다. 워크플로우가 빌드 인스턴스를 패킹해 NHN Cloud Image 서비스에 등록한 뒤, 그 이미지 ID로 테스트 인스턴스를 띄우므로 별도 Secret은 없습니다. Image API(이미지 목록 조회 등)는 [Image API 가이드](https://docs.nhncloud.com/ko/Compute/Image/ko/public-api/)를 참고하세요.

**보안 그룹 설정 필수 사항:**
- 인바운드: SSH (22), 앱 (8000), node_exporter (9100, Prometheus 스크래핑용)
- 아웃바운드: 모든 트래픽 허용 (패키지 다운로드용)

### 3. Observability 설정

| Secret 이름 | 설명 | 예시 |
|-------------|------|------|
| `LOKI_URL` | Loki 서버 URL (Promtail이 로그 전송) | `http://192.168.4.73:3100` |
| `PROMETHEUS_PUSHGATEWAY_URL` | Pushgateway URL (앱이 주기적으로 커스텀 메트릭 푸시) | `http://pushgateway:9091` |
| `PROMETHEUS_PUSH_INTERVAL_SECONDS` | Pushgateway 푸시 주기(초). 비우면 앱 기본값(30) 사용 | `30` |

**메트릭**
- **앱**: Photo API는 `http://인스턴스IP:8000/metrics` 로 Prometheus 메트릭을 노출합니다. 스크래핑 또는 Pushgateway 푸시(`PROMETHEUS_PUSHGATEWAY_URL` 설정 시) 사용.
- **인스턴스 리소스**: 이미지에 **node_exporter**가 포함되어 `http://인스턴스IP:9100/metrics` 로 호스트 메트릭(CPU, 메모리, 디스크 등)을 노출합니다. Prometheus에서 해당 타겟을 스크래핑하면 됩니다.

### 4. Photo API 애플리케이션 설정

| Secret 이름 | 설명 | 예시 |
|-------------|------|------|
| `DATABASE_URL` | 데이터베이스 연결 URL | `postgresql://user:pass@host:5432/db` |
| `JWT_SECRET_KEY` | JWT 토큰 서명 키 | `your-secret-key-min-32-chars` |
| `NHN_OBJECT_STORAGE_ENDPOINT` | NHN Object Storage endpoint | `https://kr1-api-object-storage.nhncloudservice.com` |
| `NHN_OBJECT_STORAGE_ACCESS_KEY` | Object Storage Access Key | `your-access-key` |
| `NHN_OBJECT_STORAGE_SECRET_KEY` | Object Storage Secret Key | `your-secret-key` |
| `NHN_CDN_DOMAIN` | NHN CDN 도메인 | `https://your-cdn.toastcdn.net` |
| `NHN_CDN_AUTH_KEY` | CDN 인증 키 | `your-cdn-auth-key` |

**멀티 리전:** 위 값들은 현재 워크플로에서 **이미지 빌드 시** 인스턴스 `.env`에 넣어 빌드/테스트에 사용합니다. 실제 **KR1/KR2/JP1 등 여러 리전**에 배포할 때는 **이미지에는 리전 공통 설정만 두고, 환경 변수는 배포 단계**에서 넣는 것을 권장합니다. **NHN Deploy**로 배포할 경우, Deploy 콘솔의 시나리오·서버 그룹 설정에서 리전별 `DATABASE_URL`, Object Storage/CDN 엔드포인트 등을 지정하면 됩니다. 자세한 비교는 [ENVIRONMENT_SETUP.md - 멀티 리전 배포 시 환경 변수](../ENVIRONMENT_SETUP.md#멀티-리전-배포-시-환경-변수-빌드-시-vs-배포-시)를 참고하세요.

## NHN Cloud API 인증 정보 확인 방법

### 1. API 비밀번호 설정

1. NHN Cloud Console에 로그인
2. 우측 상단 사용자 아이콘 클릭
3. **API 보안 설정** 메뉴 선택
4. **API 비밀번호 설정**에서 비밀번호 생성

### 2. 테넌트 ID 확인

1. Console > 프로젝트 설정
2. **API Endpoint** 탭에서 Tenant ID 확인

### 3. 리전 확인

- **KR1**: 한국(판교) 리전
- **KR2**: 한국(평촌) 리전  
- **JP1**: 일본(도쿄) 리전

## 워크플로우 실행 방법

### 자동 실행

다음 이벤트에서 자동으로 실행됩니다:

- `main` 또는 `develop` 브랜치에 push
- `main` 또는 `develop` 브랜치로 Pull Request 생성

### 수동 실행

1. GitHub 저장소 > Actions 탭
2. "Build and Test NHN Cloud Instance Image" 워크플로우 선택
3. "Run workflow" 버튼 클릭
4. 옵션 설정:
   - **Skip resource cleanup**: 디버깅을 위해 리소스를 삭제하지 않으려면 `true` 선택

## 워크플로우 출력

### GitHub Actions Summary

워크플로우 실행 후 Summary 탭에서 다음 정보를 확인할 수 있습니다:

- 빌드 인스턴스 ID 및 IP
- 생성된 이미지 ID 및 이름
- 테스트 인스턴스 ID 및 IP
- Git commit SHA
- 빌드 시간

### 생성된 이미지 사용

워크플로우가 성공적으로 완료되면 **NHN Cloud Image 서비스**에 등록된 이미지를 Console 또는 [Image API](https://docs.nhncloud.com/ko/Compute/Image/ko/public-api/)로 확인할 수 있습니다:

1. Console > Compute > Image (또는 Image API `GET /v2/images`로 목록 조회)
2. 이름 패턴: `photo-api-YYYYMMDD-HHMMSS`
3. 메타데이터:
   - `purpose`: `github-actions-build`
   - `app`: `photo-api`
   - `git_sha`: Git commit hash

이 이미지로 프로덕션 인스턴스를 생성할 수 있습니다.

## 트러블슈팅

### SSH 연결 실패

**증상**: "Wait for SSH to be ready" 단계에서 타임아웃

**해결 방법**:
1. 보안 그룹에 SSH (포트 22) 인바운드 규칙 확인
2. 네트워크 설정 확인 (공인 IP 할당 여부)
3. 인스턴스 플레이버가 충분한지 확인

### 패키지 설치 실패

**증상**: "Download dependencies offline" 단계에서 실패

**해결 방법**:
1. requirements.txt의 패키지 버전이 올바른지 확인
2. Promtail 버전이 존재하는지 확인
3. GitHub Actions runner에서 외부 네트워크 접근 가능한지 확인

### 이미지 생성 실패

**증상**: "Create instance image" 단계에서 타임아웃

**해결 방법**:
1. 인스턴스가 SHUTOFF 상태인지 확인
2. NHN Cloud 콘솔에서 이미지 생성 상태 확인
3. 디스크 용량이 충분한지 확인

**증상**: `An image can't be created from instance that used block storage volume` (400)

**원인**: NHN은 인스턴스 생성 시 `destination_type="volume"`만 허용하고, 그런 인스턴스에서는 Nova createImage를 막습니다.

**해결**: CI는 이 경우 **Block Storage(Volume) API**로 루트 볼륨을 이미지에 업로드하는 방식으로 대체 시도합니다. `create_build_instance` 단계에서 토큰의 서비스 카탈로그에 **volume** 서비스가 있으면 `volume_url`을 출력하고, `create_image` 단계에서 400 시 해당 URL로 `os-volume_upload_image`를 호출합니다. NHN에서 Volume API를 제공하지 않거나 실패하면 콘솔에서 수동으로 이미지를 만들거나 [Image Builder](https://docs.nhncloud.com/ko/Compute/Image%20Builder/ko/overview/)를 사용하세요.

### 401 Unauthorized (Presigned/Temp URL 업로드)

**증상**: Object Storage로 PUT 요청 시 `401 Unauthorized`

**원인 중 하나**: 서버 시간이 실제 시간과 크게 어긋나면 Temp URL의 `temp_url_expires` 서명 검증이 실패합니다.

**해결 방법**:
1. **서버 시간 확인**: 인스턴스에서 `date -u` 또는 `timedatectl`로 시간·타임존을 확인합니다.
2. **NTP 활성화**: 이 워크플로우가 만드는 이미지에는 빌드 시 `timedatectl set-ntp true`가 적용되어 있습니다. 프로덕션 인스턴스에서 NTP가 꺼져 있다면 `sudo timedatectl set-ntp true`로 활성화하세요.
3. **CI에서 검증**: "Check server time sync" 단계에서 러너와 테스트 인스턴스의 시간 차가 120초를 넘으면 실패합니다. 실패 시 해당 인스턴스의 NTP·타임존을 점검하세요.

### Health Check 실패

**증상**: "Test image with curl" 단계에서 실패

**해결 방법**:
1. 워크플로우 로그에서 디버깅 정보 확인
2. systemd 서비스 상태 확인:
   ```bash
   sudo systemctl status photo-api.service
   sudo systemctl status promtail.service
   ```
   메트릭은 앱의 `/metrics` 엔드포인트로 제공되며, Prometheus에서 스크래핑합니다.
3. 환경 변수 설정 확인: `/opt/photo-api/.env`
4. 수동 실행 시 `skip_cleanup: true`로 설정하여 인스턴스를 유지하고 직접 SSH 접속하여 디버깅

## 오프라인 환경 동작 원리

이 워크플로우는 인터넷 격리 환경에서 동작하도록 설계되었습니다:

1. **사전 다운로드**: 
   - GitHub Actions runner (인터넷 접근 가능)에서 모든 패키지를 미리 다운로드
   - Python wheels, Promtail 바이너리

2. **오프라인 설치**:
   - `pip install --no-index --find-links=/tmp/offline-packages`
   - 모든 의존성을 로컬 디렉토리에서 설치

3. **바이너리 포함**:
   - Promtail: GitHub releases에서 다운로드한 바이너리 (Loki 로그 전송)
   - Prometheus 메트릭: 앱 내장 `/metrics` 엔드포인트 (별도 에이전트 없음)
   - 런타임에 외부 네트워크 불필요

## 비용 절감 팁

1. **워크플로우 트리거 최적화**:
   - 개발 중에는 수동 실행 사용
   - PR/Push 자동 실행은 중요한 브랜치만 설정

2. **리소스 크기 조정**:
   - 빌드용으로는 작은 플레이버 사용 가능 (u2.c2m4)
   - 테스트는 최소 사양으로 충분

3. **정리 자동화**:
   - 워크플로우 종료 시 자동으로 리소스 삭제
   - 실패 시에도 cleanup 단계 실행 (`if: always()`)

## 보안 고려사항

1. **Secrets 관리**:
   - GitHub Secrets로 민감 정보 관리
   - 로그에 비밀번호나 토큰이 노출되지 않도록 주의

2. **SSH 키**:
   - 워크플로우 실행 시마다 새로운 임시 키 생성
   - 워크플로우 종료 시 키페어 자동 삭제

3. **네트워크 격리**:
   - 프로덕션 환경에서는 인터넷 차단된 VPC 사용
   - 이미지 빌드 시에만 임시로 인터넷 접근 허용

## 참고 자료

- [NHN Cloud API 가이드](https://docs.toast.com/ko/Compute/Instance/ko/api-guide/)
- [GitHub Actions 문서](https://docs.github.com/en/actions)
- [Promtail 문서](https://grafana.com/docs/loki/latest/send-data/promtail/)
- [Prometheus 문서](https://prometheus.io/docs/)
