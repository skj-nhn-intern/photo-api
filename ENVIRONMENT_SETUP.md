# 환경 변수 설정 가이드

Photo API를 실행하기 위해 필요한 환경 변수를 설정하는 방법을 안내합니다.

## 환경 변수 목록

### Application Settings

```bash
# 환경 모드 (DEV 또는 PRODUCTION)
export ENVIRONMENT=DEV

# 애플리케이션 이름
export APP_NAME="Photo API"

# 버전
export APP_VERSION=1.0.0

# 디버그 모드 (개발 시 true)
export DEBUG=true

# 시크릿 키 (운영 환경에서는 반드시 변경)
export SECRET_KEY="change-me-in-production"
```

### Database

```bash
# SQLite (개발용)
export DATABASE_URL="sqlite+aiosqlite:///./photo_api.db"

# PostgreSQL (운영 환경 권장)
# export DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/photo_api"
```

### JWT Settings

```bash
export JWT_SECRET_KEY="jwt-secret-change-in-production"
export JWT_ALGORITHM="HS256"
export ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### NHN Cloud Object Storage (IAM 인증)

**NHN Cloud 콘솔에서 확인:**
1. NHN Cloud Console 로그인
2. **Storage > Object Storage** 메뉴
3. **컨테이너** 생성 (예: `photo-container`)
4. **API 엔드포인트 설정** 탭에서 인증 정보 확인

```bash
# IAM 사용자명 (API 사용자명)
export NHN_STORAGE_IAM_USER="your-iam-username"

# IAM 비밀번호 (API 비밀번호)
export NHN_STORAGE_IAM_PASSWORD="your-iam-password"

# 프로젝트 ID
export NHN_STORAGE_PROJECT_ID="your-project-id"

# Tenant ID
export NHN_STORAGE_TENANT_ID="your-tenant-id"

# IAM 인증 URL (한국 리전)
export NHN_STORAGE_AUTH_URL="https://api-identity-infrastructure.nhncloudservice.com/v2.0"

# 컨테이너 이름
export NHN_STORAGE_CONTAINER="photo-container"

# Object Storage URL (한국 리전)
export NHN_STORAGE_URL="https://api-storage.nhncloudservice.com/v1"
```

### NHN Cloud Object Storage S3 API (Presigned URL 사용)

**S3 API 자격 증명 발급 방법:**

참조: https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/s3-api-guide/#s3-api-s3-api-credential

1. NHN Cloud Console 로그인
2. **Storage > Object Storage** 메뉴
3. **API 엔드포인트 설정** 탭
4. **S3 API 자격 증명** 섹션에서 **S3 API 자격 증명 발급** 클릭
5. Access Key와 Secret Key 복사

```bash
# S3 API Access Key (EC2 credentials)
export NHN_S3_ACCESS_KEY="your-s3-access-key"

# S3 API Secret Key
export NHN_S3_SECRET_KEY="your-s3-secret-key"

# S3 API Endpoint URL (한국 리전)
export NHN_S3_ENDPOINT_URL="https://kr1-api-object-storage.nhncloudservice.com"

# S3 Region Name
export NHN_S3_REGION_NAME="kr1"

# Presigned URL 유효 시간 (초) - 기본 1시간
export NHN_S3_PRESIGNED_URL_EXPIRE_SECONDS=3600
```

### NHN Cloud CDN (Auth Token API)

**NHN Cloud 콘솔에서 확인:**
1. **Content Delivery > CDN** 메뉴
2. CDN 서비스 생성
3. **Auth Token** 설정 활성화
4. **Token Encryption Key** 발급

참조: https://docs.nhncloud.com/ko/Contents%20Delivery/CDN/ko/api-guide-v2.0/#auth-token-api

```bash
# CDN 도메인 (예: xxx.toastcdn.net)
export NHN_CDN_DOMAIN="your-cdn-domain.toastcdn.net"

# CDN App Key
export NHN_CDN_APP_KEY="your-cdn-app-key"

# CDN API Secret Key
export NHN_CDN_SECRET_KEY="your-cdn-api-secret-key"

# CDN Token Encryption Key
export NHN_CDN_ENCRYPT_KEY="your-cdn-encrypt-key"

# Auth Token 유효 시간 (초) - 기본 1시간
export NHN_CDN_TOKEN_EXPIRE_SECONDS=3600
```

### NHN Cloud Log & Crash

**NHN Cloud 콘솔에서 확인:**
1. **Log & Crash Search** 메뉴
2. 프로젝트 생성
3. **URL & Appkey** 확인

```bash
# Log & Crash Appkey
export NHN_LOG_APPKEY="your-log-appkey"

# Log & Crash URL
export NHN_LOG_URL="https://api-logncrash.nhncloudservice.com/v2/log"

# 로그 버전
export NHN_LOG_VERSION="v2"

# 플랫폼
export NHN_LOG_PLATFORM="API"
```

### Prometheus (Observability)

```bash
# 노드 이름 (서버 식별용)
export NODE_NAME="photo-api-node-1"

# 인스턴스 IP (비우면 자동 감지)
export INSTANCE_IP=""
```

## 환경 변수 설정 방법

### 1. 터미널에서 직접 설정 (임시)

```bash
export NHN_S3_ACCESS_KEY="your-key"
export NHN_S3_SECRET_KEY="your-secret"
# ... 나머지 환경 변수
```

### 2. `.env` 파일 사용 (개발 환경)

프로젝트 루트에 `.env` 파일 생성:

```bash
# .env
NHN_S3_ACCESS_KEY=your-key
NHN_S3_SECRET_KEY=your-secret
# ... 나머지 환경 변수
```

> ⚠️ **주의**: `.env` 파일은 Git에 커밋하지 마세요! (`.gitignore`에 추가되어 있습니다)

### 3. systemd 환경 파일 (운영 환경 - Linux)

`/etc/default/photo-api` 파일 생성:

```bash
# /etc/default/photo-api
NHN_S3_ACCESS_KEY=your-key
NHN_S3_SECRET_KEY=your-secret
# ... 나머지 환경 변수
```

systemd 서비스 파일에서 참조:

```ini
[Service]
EnvironmentFile=/etc/default/photo-api
```

### 4. Docker 환경 변수

`docker-compose.yml`:

```yaml
version: '3.8'
services:
  photo-api:
    image: photo-api:latest
    environment:
      - NHN_S3_ACCESS_KEY=your-key
      - NHN_S3_SECRET_KEY=your-secret
      # ... 나머지 환경 변수
    # 또는 env_file 사용
    env_file:
      - .env
```

### 5. Kubernetes ConfigMap/Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: photo-api-secrets
type: Opaque
stringData:
  NHN_S3_ACCESS_KEY: your-key
  NHN_S3_SECRET_KEY: your-secret
  # ... 나머지 환경 변수
```

Deployment에서 참조:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: photo-api
spec:
  template:
    spec:
      containers:
      - name: photo-api
        image: photo-api:latest
        envFrom:
        - secretRef:
            name: photo-api-secrets
```

## 환경 변수 검증

서버 시작 시 필수 환경 변수가 설정되지 않으면 에러가 발생합니다:

```python
# 예시
if not self.settings.nhn_s3_access_key or not self.settings.nhn_s3_secret_key:
    raise Exception(
        "S3 API credentials not configured. "
        "Please set NHN_S3_ACCESS_KEY and NHN_S3_SECRET_KEY environment variables."
    )
```

## 보안 고려사항

1. **시크릿 키 보호**
   - 운영 환경에서는 강력한 랜덤 키 사용
   - Git 저장소에 절대 커밋하지 않기
   - 환경별로 다른 키 사용

2. **접근 제어**
   - 환경 변수 파일의 권한 제한 (chmod 600)
   - 최소 권한 원칙 적용

3. **키 로테이션**
   - 정기적으로 S3 API 키 갱신
   - JWT 시크릿 키 주기적 변경

4. **환경 분리**
   - 개발/스테이징/운영 환경별 다른 자격 증명 사용

## 문제 해결

### S3 API 자격 증명 오류

```
Exception: S3 API credentials not configured.
```

**해결 방법:**
- `NHN_S3_ACCESS_KEY`와 `NHN_S3_SECRET_KEY` 환경 변수 확인
- NHN Cloud Console에서 S3 API 자격 증명 재발급

### IAM 인증 오류

```
IAM 인증 실패: 인증 정보가 올바르지 않습니다.
```

**해결 방법:**
- `NHN_STORAGE_IAM_USER`, `NHN_STORAGE_IAM_PASSWORD`, `NHN_STORAGE_TENANT_ID` 확인
- NHN Cloud Console에서 API 엔드포인트 설정 확인

### 데이터베이스 연결 오류

```
Could not connect to database
```

**해결 방법:**
- `DATABASE_URL` 환경 변수 확인
- 데이터베이스 서버 실행 상태 확인
- 네트워크 연결 확인

## 멀티 리전 배포 시 환경 변수: 빌드 시 vs 배포 시

추후 **멀티 리전**으로 배포할 경우, 환경 변수는 **빌드할 때 넣지 말고, 배포(또는 런타임)할 때 넣는 것**을 권장합니다.

| 구분 | 빌드 시 주입 | 배포/런타임 시 주입 |
|------|----------------|----------------------|
| **이미지/아티팩트** | 리전마다 다른 값을 넣으면 **리전별로 다른 이미지**를 빌드해야 함 | **동일 이미지** 하나를 모든 리전에 배포 가능 |
| **리전별 차이** | KR1/KR2 등 엔드포인트·DB·CDN이 다름 → 빌드 분리 필요 | 배포 시점에 `NHN_STORAGE_URL`, `NHN_S3_ENDPOINT_URL`, `NHN_S3_REGION_NAME`, `DATABASE_URL` 등만 리전별로 설정 |
| **비밀값** | 이미지에 박히면 보안·로테이션 불리 | Secret/ConfigMap·systemd EnvironmentFile 등으로 주입 권장 |
| **변경** | 설정 바꿀 때마다 재빌드 필요 | 같은 이미지 유지, 배포 설정만 수정 |

**정리:** Photo API는 이미 `config.py`에서 **앱 기동 시 환경 변수**를 읽습니다. 따라서 **한 번만 빌드**하고, 각 리전 배포 시 해당 리전용 환경 변수만 넣으면 됩니다.

- **KR1**: `NHN_STORAGE_URL=https://kr1-api-object-storage.nhncloudservice.com/v1`, `NHN_S3_ENDPOINT_URL=https://kr1-api-object-storage.nhncloudservice.com`, `NHN_S3_REGION_NAME=kr1`, 리전별 DB/CDN 등
- **KR2**: 위와 동일 이미지, `kr2-...` URL 및 `kr2` 리전 등으로만 환경 변수 변경

CI/CD에서는 이미지는 공통으로 빌드하고, 배포 스테이지에서 리전별 env만 주입하도록 구성하면 됩니다. **NHN Deploy**를 사용할 경우, Deploy 콘솔의 배포 시나리오·서버 그룹 설정에서 `DATABASE_URL`, Object Storage/CDN 엔드포인트 등 리전별 환경 변수를 지정하면 됩니다. ([NHN Cloud Deploy 가이드](https://docs.nhncloud.com/ko/Dev%20Tools/Deploy/ko/console-guide/) 참고)

## 참고 자료

- [NHN Cloud Deploy 콘솔 가이드](https://docs.nhncloud.com/ko/Dev%20Tools/Deploy/ko/console-guide/) (배포 시 환경 변수 등)
- [NHN Cloud Object Storage 문서](https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/overview/)
- [S3 API 가이드](https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/s3-api-guide/)
- [CDN Auth Token API 가이드](https://docs.nhncloud.com/ko/Contents%20Delivery/CDN/ko/api-guide-v2.0/#auth-token-api)
- [Presigned URL 사용 가이드](./PRESIGNED_URL_GUIDE.md)
