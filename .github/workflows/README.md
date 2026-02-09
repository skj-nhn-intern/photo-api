# GitHub Actions Workflows

이 디렉토리는 photo-api의 CI/CD 워크플로우를 포함합니다.

## 워크플로우 목록

### 🏗️ build-and-test-image.yml

**목적**: NHN Cloud 인스턴스 이미지를 빌드하고 테스트합니다.

**주요 기능**:
- ✅ 인터넷 격리 환경을 위한 오프라인 패키지 준비
- ✅ Python 3.11 + FastAPI + 의존성 패키지 설치
- ✅ Promtail 바이너리 포함 (Loki 로깅)
- ✅ Prometheus 메트릭 (/metrics 엔드포인트, 앱 내장)
- ✅ systemd 서비스 자동 등록 및 활성화
- ✅ 이미지 생성 및 테스트 인스턴스 검증
- ✅ Health check 및 Prometheus metrics 확인
- ✅ 자동 리소스 정리

**트리거**:
- `main`, `develop` 브랜치 push
- `main`, `develop` 브랜치 대상 Pull Request
- 수동 실행 (workflow_dispatch)

**실행 시간**: 약 20-30분

**필수 Secrets**: 
- NHN Cloud 인증 (7개)
- Observability (1개: LOKI_URL)
- Application 설정 (7개)

자세한 설정 방법은 [GITHUB_ACTIONS_SETUP.md](../GITHUB_ACTIONS_SETUP.md)를 참조하세요.

## 빠른 시작

### 1. Secrets 설정

```bash
# GitHub CLI 사용 예시
gh secret set NHN_AUTH_URL -b"https://api-identity-infrastructure.nhncloudservice.com/v2.0"
gh secret set NHN_TENANT_ID -b"your-tenant-id"
gh secret set NHN_USERNAME -b"your-username"
gh secret set NHN_PASSWORD -b"your-password"
# ... (나머지 secrets)
```

또는 GitHub 웹 인터페이스에서:
1. Repository > Settings > Secrets and variables > Actions
2. "New repository secret" 클릭
3. 필요한 모든 secrets 추가

### 2. 워크플로우 수동 실행

```bash
# GitHub CLI 사용
gh workflow run build-and-test-image.yml

# 디버깅 모드 (리소스 정리 건너뛰기)
gh workflow run build-and-test-image.yml -f skip_cleanup=true
```

또는 GitHub 웹 인터페이스에서:
1. Actions 탭 이동
2. "Build and Test NHN Cloud Instance Image" 선택
3. "Run workflow" 버튼 클릭

### 3. 실행 결과 확인

워크플로우가 성공하면:

1. **Summary 탭**에서 생성된 이미지 정보 확인
2. **NHN Cloud Console**에서 이미지 확인:
   - Console > Compute > Image
   - 이름: `photo-api-YYYYMMDD-HHMMSS`

## 워크플로우 단계 설명

| 단계 | 설명 | 소요 시간 |
|------|------|----------|
| 1. Checkout code | 소스 코드 체크아웃 | ~10초 |
| 2. Create build instance | NHN Cloud에 빌드용 인스턴스 생성 | ~3분 |
| 3. Download dependencies | Python 패키지, Promtail 다운로드 | ~2분 |
| 4. Upload packages | 패키지를 빌드 인스턴스에 업로드 | ~1분 |
| 5. Build image | 오프라인 설치 및 systemd 설정 | ~5분 |
| 6. Create image snapshot | 인스턴스를 이미지로 스냅샷 | ~5분 |
| 7. Create test instance | 생성된 이미지로 테스트 인스턴스 시작 | ~3분 |
| 8. Test with curl | Health check 및 metrics 확인 | ~1분 |
| 9. Cleanup | 리소스 정리 (인스턴스, 키페어 삭제) | ~1분 |

## 생성된 이미지 구조

이미지에는 다음이 포함됩니다:

```
/opt/photo-api/
├── app/                    # FastAPI 애플리케이션 (Prometheus /metrics 내장)
├── venv/                   # Python 가상환경 (모든 의존성 포함)
├── requirements.txt
├── conf/
│   └── promtail-config.yaml
└── .env                    # 환경 변수

/opt/promtail/
├── promtail                # 바이너리
└── promtail-config.yaml

/var/log/photo-api/         # 로그 디렉토리
├── app.log
└── error.log

/etc/systemd/system/
├── photo-api.service       # 자동 시작 설정됨
└── promtail.service        # 자동 시작 설정됨
```

**메트릭**: Photo API는 `/metrics` 엔드포인트로 Prometheus 메트릭을 노출합니다. Prometheus 서버에서 해당 인스턴스를 스크래핑 대상으로 등록하면 됩니다. (Telegraf/InfluxDB 미사용)

## 트러블슈팅

### ❌ "SSH 연결 실패"

**해결**: 
- 보안 그룹에 SSH (22번 포트) 인바운드 규칙 추가
- 인스턴스에 공인 IP 할당 확인

### ❌ "Health check 실패"

**해결**:
1. 수동 실행 시 `skip_cleanup: true` 설정
2. 테스트 인스턴스에 SSH 접속:
   ```bash
   ssh ubuntu@<test_instance_ip>
   sudo systemctl status photo-api
   sudo journalctl -u photo-api -f
   ```
3. 환경 변수 확인: `cat /opt/photo-api/.env`

### ❌ "패키지 다운로드 실패"

**해결**:
- requirements.txt의 패키지 버전 확인
- Promtail 버전이 유효한지 확인

### 🔍 디버깅 모드

리소스를 유지하고 직접 접속하려면:

```bash
gh workflow run build-and-test-image.yml -f skip_cleanup=true
```

워크플로우 완료 후:
1. Actions 로그에서 인스턴스 IP 확인
2. SSH 키는 GitHub Actions runner에만 존재하므로 별도 키페어 등록 필요
3. NHN Cloud Console에서 키페어 추가 후 접속

## 환경별 설정

### 개발 환경

```yaml
# .github/workflows/build-and-test-image-dev.yml
on:
  push:
    branches:
      - develop
```

### 프로덕션 환경

```yaml
# .github/workflows/build-and-test-image-prod.yml
on:
  push:
    branches:
      - main
    tags:
      - 'v*'
```

환경별로 다른 secrets를 사용하려면 GitHub Environments를 활용하세요:
1. Settings > Environments
2. 환경 생성 (예: `development`, `production`)
3. 환경별 secrets 설정
4. 워크플로우에서 `environment` 지정

```yaml
jobs:
  build-and-test:
    environment: production
    steps:
      # ...
```

## 비용 최적화

### 워크플로우 실행 횟수 줄이기

```yaml
# 특정 파일 변경 시에만 실행
on:
  push:
    paths:
      - 'app/**'
      - 'requirements.txt'
      - 'scripts/**'
      - 'conf/**'
```

### 작은 플레이버 사용

빌드 및 테스트용으로는 최소 사양으로 충분합니다:
- `u2.c2m4`: vCPU 2개, RAM 4GB

### 병렬 실행 제한

```yaml
concurrency:
  group: build-image-${{ github.ref }}
  cancel-in-progress: true
```

## 인스턴스 이미지 배포 파이프라인을 더 효율적으로 구축하려면

원래 목적인 **인스턴스 이미지화 + 배포 파이프라인**을 유지하면서, 비용·시간·유지보수를 줄이려면 아래를 권장합니다.

### 1. Job 분리 + 캐시 (권장)

**현재**: 한 job에서 체크아웃 → 인스턴스 생성 → 의존성 다운로드 → 업로드 → 빌드 → 이미지 생성 → 테스트 → 정리까지 모두 순차 실행. 매 실행마다 `pip download`, Promtail 다운로드를 반복합니다.

**개선**:
- **Job 1 – prepare**: 체크아웃, `pip download -r requirements.txt`, Promtail 다운로드 → **캐시** (cache key: `requirements.txt` 해시 또는 lock 파일). 산출물을 artifact로 업로드.
- **Job 2 – build-image** (Job 1 의존): artifact 다운로드 → 인스턴스 생성 → 업로드(소스 + artifact) → 빌드 → 스냅샷 → 테스트 → 정리.

효과: 의존성이 바뀌지 않으면 캐시 hit으로 2~3분 절약, artifact 재사용으로 runner 부담 감소.

### 2. 이미지 생성은 필요할 때만 (조건부 실행)

**현재**: `main`/`develop` push, PR 모두에서 동일하게 인스턴스 생성·이미지 생성까지 수행합니다.

**개선**:
- **실제 이미지 생성(스냅샷 + 테스트 인스턴스)** 은 `main` 브랜치 push 또는 `v*` 태그 push 시에만 실행.
- **PR / develop**:  
  - 옵션 A: 로컬/CI에서 **코드 검증만** (pytest, lint) 하고, NHN 인스턴스 이미지 빌드는 하지 않음.  
  - 옵션 B: 이미지 빌드 job은 `if: github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v')` 로 제한.

효과: PR·develop 빌드 시 인스턴스 비용과 20~30분 대기 시간 제거.

### 3. 재사용 가능한 스크립트로 분리

**현재**: NHN API 호출(인스턴스 생성/중지/이미지 생성/삭제 등)이 워크플로우 안에 700줄 가까운 인라인 Python으로 들어 있습니다.

**개선**:
- `scripts/nhn-compute-*.py` 또는 **composite action**으로 분리  
  - 예: `create-instance`, `create-image-from-instance`, `delete-instance`, `cleanup-keypair`  
- 워크플로우는 `run: python scripts/nhn-compute-create-instance.py` 형태로 호출만 하도록 정리.

효과: 수정·재사용·테스트가 쉬워지고, 멀티 리전/다른 프로젝트에서도 같은 스크립트를 쓸 수 있음.

### 4. Packer 도입 검토 (선택)

NHN Cloud에 **Packer builder** 또는 호환되는 이미지 빌드 방식이 있다면:
- 이미지 내용을 **Packer 템플릿**으로 정의 (프로비저닝 스크립트, systemd 유닛 등).
- CI에서는 `packer build photo-api.pkr.hcl` 한 번만 실행.
- 인스턴스 생성·SSH·스냅샷은 Packer가 처리하고, 워크플로우는 짧게 유지.

효과: 이미지 빌드 과정이 선언적·표준화되고, 로컬에서도 동일하게 `packer build`로 검증 가능.

### 5. 정리: 권장 순서

| 순서 | 내용 | 효과 |
|------|------|------|
| 1 | **이미지 생성 조건부화** (main/tag만) | 비용·시간 절감이 가장 큼 |
| 2 | **오프라인 패키지 캐시 + job 분리** | 반복 실행 시간 단축 |
| 3 | **NHN API 스크립트 분리** (또는 composite action) | 유지보수·재사용 용이 |
| 4 | (선택) **Packer** 도입 | 이미지 빌드 표준화 |

현재 `build-and-test-image.yml`은 위 1~3만 적용해도, PR 시에는 테스트만 돌리고 main/tag에서만 이미지를 만들도록 바꾸면 효율적인 **인스턴스 이미지 배포 파이프라인**으로 정리할 수 있습니다.

## 참고 자료

- 📚 [전체 설정 가이드](../GITHUB_ACTIONS_SETUP.md)
- 🏗️ [빌드 스크립트 문서](../../scripts/README.md)
- 🌐 [NHN Cloud API 문서](https://docs.toast.com/ko/Compute/Instance/ko/api-guide/)
