# Photo API

FastAPI 기반의 사진 관리 API 서버입니다. NHN Cloud의 Object Storage, CDN, Log & Crash 서비스와 연동됩니다.

## 주요 기능

### 사용자 관리
- 회원가입 (`POST /auth/register`)
- 로그인 (`POST /auth/login`)
- JWT 기반 인증

### 사진 관리
- **Presigned URL 업로드** (`POST /photos/presigned-url`) - **권장 방식**
  - 클라이언트가 Object Storage에 직접 업로드
  - 서버 부하 감소, 업로드 속도 향상
- 사진 업로드 (`POST /photos/`) - 레거시 직접 업로드 방식
- 사진 조회 (`GET /photos/`, `GET /photos/{id}`)
- 사진 수정/삭제 (`PATCH /photos/{id}`, `DELETE /photos/{id}`)
- 업로드 완료 확인 (`POST /photos/confirm`)
.g

### 앨범 관리
- 앨범 생성/조회/수정/삭제
- 앨범에 사진 추가/제거
- 앨범 공유 링크 생성

### 공유 기능
- 공유 링크 생성 (`POST /albums/{id}/share`)
- 공유 링크로 앨범 접근 (`GET /share/{token}`)
- 로그인 없이 앨범 열람 가능

## 기술 스택

- **FastAPI**: 비동기 웹 프레임워크
- **SQLAlchemy 2.0**: 비동기 ORM
- **Pydantic v2**: 데이터 검증
- **NHN Cloud Object Storage**: 파일 저장소
- **NHN Cloud CDN**: Auth Token 기반 콘텐츠 전송
- **NHN Cloud Log & Crash**: 중앙 집중식 로깅

## 프로젝트 구조

```
photo-api/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 앱 엔트리포인트
│   ├── config.py            # 환경 설정
│   ├── database.py          # DB 연결 관리
│   ├── models/              # SQLAlchemy 모델
│   │   ├── user.py
│   │   ├── photo.py
│   │   ├── album.py
│   │   └── share.py
│   ├── schemas/             # Pydantic 스키마
│   │   ├── user.py
│   │   ├── photo.py
│   │   ├── album.py
│   │   └── share.py
│   ├── routers/             # API 라우터
│   │   ├── auth.py
│   │   ├── photos.py
│   │   ├── albums.py
│   │   └── share.py
│   ├── services/            # 비즈니스 로직
│   │   ├── auth.py
│   │   ├── photo.py
│   │   ├── album.py
│   │   ├── nhn_object_storage.py
│   │   ├── nhn_cdn.py
│   │   └── nhn_logger.py
│   ├── dependencies/        # FastAPI 의존성
│   │   └── auth.py
│   └── utils/               # 유틸리티 함수
│       └── security.py
├── requirements.txt
└── README.md
```

## 설치 및 실행

### 1. 가상환경 생성 및 활성화

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# Windows: venv\Scripts\activate
```

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. 환경 변수 설정

`.env` 파일을 생성하고 아래 내용을 설정합니다:

```env
# Application Settings
APP_NAME=Photo API
APP_VERSION=1.0.0
DEBUG=true
SECRET_KEY=your-secret-key-change-in-production

# Database
DATABASE_URL=sqlite+aiosqlite:///./photo_api.db
# PostgreSQL: postgresql+asyncpg://user:password@localhost:5432/photo_api

# JWT Settings
JWT_SECRET_KEY=your-jwt-secret-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# NHN Cloud Object Storage (IAM 인증)
NHN_STORAGE_TENANT_ID=your-tenant-id
NHN_STORAGE_IAM_USER=your-iam-username
NHN_STORAGE_IAM_PASSWORD=your-iam-password
NHN_STORAGE_AUTH_URL=https://api-identity-infrastructure.nhncloudservice.com/v2.0
NHN_STORAGE_CONTAINER=photo-container
NHN_STORAGE_URL=https://api-storage.nhncloudservice.com/v1

# NHN Cloud Object Storage S3 API (Presigned URL 사용)
NHN_S3_ACCESS_KEY=your-s3-access-key
NHN_S3_SECRET_KEY=your-s3-secret-key
NHN_S3_ENDPOINT_URL=https://kr1-api-object-storage.nhncloudservice.com
NHN_S3_REGION_NAME=kr1
NHN_S3_PRESIGNED_URL_EXPIRE_SECONDS=3600

# NHN Cloud CDN
NHN_CDN_DOMAIN=your-cdn-domain.toastcdn.net
NHN_CDN_SECRET_KEY=your-cdn-secret-key
NHN_CDN_TOKEN_EXPIRE_SECONDS=3600

# NHN Cloud Log & Crash
NHN_LOG_APPKEY=your-log-appkey
NHN_LOG_URL=https://api-logncrash.nhncloudservice.com/v2/log
```

### 4. 서버 실행

```bash
uvicorn app.main:app --reload
```

서버가 시작되면 http://localhost:8000 에서 접근할 수 있습니다.

### 5. API 문서 확인

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API 사용 예시

### 회원가입

```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "username": "myuser",
    "password": "mypassword123"
  }'
```

### 로그인

```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "mypassword123"
  }'
```

응답에서 `access_token`을 받아 이후 요청에 사용합니다.

### 사진 업로드 (Presigned URL 방식 - 권장)

**자세한 사용 방법은 [PRESIGNED_URL_GUIDE.md](./PRESIGNED_URL_GUIDE.md) 참조**

```bash
# 1. Presigned URL 발급
curl -X POST "http://localhost:8000/photos/presigned-url" \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "album_id": 1,
    "filename": "photo.jpg",
    "content_type": "image/jpeg",
    "file_size": 1024000,
    "title": "My Photo"
  }'

# 2. Object Storage에 직접 업로드 (응답에서 받은 upload_url 사용)
curl -X PUT "{upload_url}" \
  -H "Content-Type: image/jpeg" \
  --data-binary "@photo.jpg"

# 3. 업로드 완료 확인 (응답에서 받은 photo_id 사용)
curl -X POST "http://localhost:8000/photos/confirm" \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{"photo_id": 123}'
```

### 사진 업로드 (레거시 직접 업로드 방식)

```bash
curl -X POST "http://localhost:8000/photos/" \
  -H "Authorization: Bearer {access_token}" \
  -F "file=@/path/to/photo.jpg" \
  -F "album_id=1" \
  -F "title=My Photo"
```

### 앨범 생성

```bash
curl -X POST "http://localhost:8000/albums/" \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Album",
    "description": "My first album"
  }'
```

### 공유 링크 생성

```bash
curl -X POST "http://localhost:8000/albums/{album_id}/share" \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "expires_in_days": 7
  }'
```

### 공유 링크로 앨범 접근 (인증 불필요)

```bash
curl "http://localhost:8000/share/{token}"
```

## 핵심 흐름

### 사진 업로드 흐름 (Presigned URL 방식 - 권장)

1. 클라이언트가 서버에 메타데이터 전송 (파일 크기, 타입 등)
2. 서버가 DB에 사진 메타데이터 저장 및 Presigned URL 생성
3. 클라이언트가 Presigned URL을 사용하여 Object Storage에 직접 업로드
4. 클라이언트가 서버에 업로드 완료 확인 요청
5. 서버가 Object Storage에서 파일 존재 확인 후 응답

**장점:**
- 서버 부하 감소 (파일이 서버를 거치지 않음)
- 업로드 속도 향상 (직접 연결)
- 서버 대역폭 절약

### 사진 업로드 흐름 (레거시 직접 업로드 방식)

1. 클라이언트가 사진 파일과 메타데이터를 서버에 전송
2. 서버가 NHN Cloud Object Storage에 파일 업로드
3. 서버가 사진 메타데이터를 DB에 저장
4. 클라이언트에게 업로드 완료 응답

### 사진 조회 흐름

1. 클라이언트가 사진 조회 요청
2. 서버가 DB에서 사진 메타데이터 조회
3. 서버가 CDN Auth Token이 포함된 URL 생성
4. 클라이언트가 해당 URL로 CDN에서 이미지 다운로드

### 공유 링크 흐름

1. 앨범 소유자가 공유 링크 생성 요청
2. 서버가 랜덤 토큰 생성 및 DB에 저장
3. 외부 사용자가 공유 링크로 접근
4. 서버가 앨범 정보와 CDN URL 반환
5. 클라이언트가 CDN에서 이미지 로드

## 배포

### 인스턴스 이미지 빌드

이 프로젝트는 인터넷 격리 환경에서 실행 가능한 NHN Cloud 인스턴스 이미지를 자동으로 빌드합니다.

#### 포함된 구성 요소

- **Python 3.11** + FastAPI + 모든 의존성 패키지
- **Promtail**: Loki로 로그 전송
- **Prometheus 메트릭**: 앱 `/metrics` 엔드포인트 (스크래핑). 추후 [Pushgateway](PROMETHEUS_PUSHGATEWAY.md) 연동 시 주기 푸시 지원
- **systemd 서비스**: 자동 시작 설정

#### 수동 빌드

```bash
# 로컬에서 빌드 스크립트 실행
sudo ./scripts/build-image.sh
```

자세한 내용은 [scripts/README.md](scripts/README.md)를 참조하세요.

#### NHN Deploy로 환경 변수 배포

이미지로 만든 인스턴스에 **리전별 환경 변수**를 넣고 서비스를 재시작하려면 [deploy/README.md](deploy/README.md)를 참고하세요. `deploy/apply-env-and-restart.sh`를 NHN Deploy User Command로 실행하면 됩니다.

#### GitHub Actions를 통한 자동 빌드

GitHub Actions 워크플로우를 사용하면 자동으로 인스턴스 이미지를 빌드하고 테스트할 수 있습니다.

**주요 기능:**
- ✅ 오프라인 패키지 사전 다운로드 (Python, Promtail)
- ✅ NHN Cloud에 빌드 인스턴스 생성
- ✅ 인터넷 격리 환경에서 오프라인 설치
- ✅ 인스턴스 이미지 스냅샷 생성
- ✅ 테스트 인스턴스에서 동작 검증 (curl health check)
- ✅ 자동 리소스 정리

**설정 방법:**

1. GitHub Secrets 설정 (필수):
   ```bash
   # NHN Cloud 인증 정보
   NHN_AUTH_URL, NHN_TENANT_ID, NHN_USERNAME, NHN_PASSWORD
   NHN_REGION, NHN_FLAVOR_NAME, NHN_IMAGE_NAME, NHN_NETWORK_ID
   
   # Observability (메트릭은 Prometheus가 /metrics 스크래핑)
   LOKI_URL
   
   # Application
   DATABASE_URL, JWT_SECRET_KEY, NHN_OBJECT_STORAGE_*, NHN_CDN_*
   ```

2. 워크플로우 실행:
   ```bash
   # 수동 실행
   gh workflow run build-and-test-image.yml
   
   # 또는 main/develop 브랜치에 push하면 자동 실행
   git push origin main
   ```

3. 생성된 이미지 확인:
   - NHN Cloud Console > Compute > Image
   - 이미지 이름: `photo-api-YYYYMMDD-HHMMSS`

**자세한 가이드:**
- [GitHub Actions 설정 가이드](.github/GITHUB_ACTIONS_SETUP.md)
- [워크플로우 문서](.github/workflows/README.md)

#### 오프라인 빌드 테스트

GitHub Actions를 실행하기 전에 로컬에서 오프라인 빌드를 테스트할 수 있습니다:

```bash
./scripts/test-offline-build.sh
```

이 스크립트는 GitHub Actions 워크플로우를 시뮬레이션하여 다음을 확인합니다:
- Python 패키지 오프라인 다운로드 및 설치
- Promtail 바이너리 다운로드 및 압축 해제
- 모든 Python 모듈 import 테스트

## 로깅 (Logging)

Photo API는 **구조화된 로깅 (Structured Logging)** 을 사용하여 효과적인 장애 추적과 분석을 지원합니다.

### 주요 특징

- **JSON 형식**: 로그를 JSON으로 출력하여 집계 및 분석 용이
- **로그 레벨 전략**: ERROR, WARN, INFO, DEBUG 레벨별 명확한 용도 정의
- **풍부한 컨텍스트**: 요청 정보, 인프라 정보, 오류 정보 등 자동 포함
- **Request ID**: 모든 요청에 고유 ID를 부여하여 추적 가능
- **자동 로깅**: 미들웨어를 통한 HTTP 요청/응답 자동 로깅

### 로그 레벨 전략

| **레벨** | **용도** | **예시** |
|:-------:|:---------|:---------|
| **ERROR** | 즉시 대응 필요한 오류 | DB 연결 실패, 외부 API 장애 |
| **WARN** | 잠재적 문제, 곧 이슈가 될 수 있음 | 재시도 발생, 임계치 근접 |
| **INFO** | 주요 비즈니스 이벤트 | 사용자 로그인, 사진 업로드 |
| **DEBUG** | 개발/디버깅용 상세 정보 | 함수 진입/종료, 변수 값 |

### 기본 사용법

```python
from app.utils.logger import log_info, log_warning, log_error

# INFO: 주요 비즈니스 이벤트
log_info("User login successful", event="user_login", user_id=12345)

# WARNING: 잠재적 문제
log_warning("API rate limit approaching", current_rate=950, limit=1000)

# ERROR: 즉시 대응 필요
log_error(
    "Database connection failed",
    error_type="DatabaseError",
    error_code="DB_001",
    upstream_service="postgresql",
    exc_info=True
)
```

### 클라이언트 IP 처리

규역 준수를 위해 모든 로그에 실제 클라이언트 IP가 명시됩니다.

- **프론트엔드**: 추가 설정 불필요 (브라우저가 자동으로 전송)
- **NHN Cloud API Gateway**: 자동으로 `X-Forwarded-For` 헤더 추가
- **NHN Cloud Load Balancer**: 리스너 설정에서 활성화 필요
- **백엔드**: 프록시 헤더 자동 처리 (이미 구현됨)

**테스트 방법:**
```bash
curl https://your-api-url/debug/client-info | jq '.client_ip'
```

### 자세한 가이드

- [구조화된 로깅 가이드](./STRUCTURED_LOGGING_GUIDE.md): 로깅 시스템 사용법
- [NHN Cloud 환경 클라이언트 IP 가이드](../NHN_CLOUD_CLIENT_IP_GUIDE.md): API Gateway/Load Balancer 설정

## 설계 원칙

### 메모리 누수 방지
- 비동기 DB 세션의 적절한 생명주기 관리
- Connection Pool 설정으로 DB 연결 관리
- Context Manager를 통한 리소스 정리

### FastAPI 장점 활용
- 비동기 처리로 높은 동시성 지원
- Pydantic을 통한 자동 데이터 검증
- 의존성 주입을 통한 코드 재사용
- 자동 OpenAPI 문서 생성

### 로깅 시스템 성능 최적화
- 비동기 백그라운드 큐로 로그 처리
- 로그 배치 전송으로 네트워크 오버헤드 감소
- 큐 크기 제한으로 메모리 보호

### 객체지향 설계
- 서비스 계층으로 비즈니스 로직 분리
- 의존성 주입을 통한 테스트 용이성
- 단일 책임 원칙 준수

### 인터넷 격리 환경 지원
- 모든 의존성을 이미지에 사전 포함
- 오프라인 패키지 설치 지원
- 바이너리 파일 (Promtail) 포함
- 런타임에 외부 네트워크 불필요

## 라이선스

MIT License
