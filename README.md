# Photo API

FastAPI 기반의 사진 관리 API 서버입니다. NHN Cloud의 Object Storage, CDN, Log & Crash 서비스와 연동됩니다.

## 주요 기능

### 사용자 관리
- 회원가입 (`POST /auth/register`)
- 로그인 (`POST /auth/login`)
- JWT 기반 인증

### 사진 관리
- 사진 업로드 (`POST /photos/`)
- 사진 조회 (`GET /photos/`, `GET /photos/{id}`)
- 사진 수정/삭제 (`PATCH /photos/{id}`, `DELETE /photos/{id}`)

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

# NHN Cloud Object Storage
NHN_STORAGE_TENANT_ID=your-tenant-id
NHN_STORAGE_USERNAME=your-username
NHN_STORAGE_PASSWORD=your-password
NHN_STORAGE_AUTH_URL=https://api-identity-infrastructure.nhncloudservice.com/v2.0
NHN_STORAGE_CONTAINER=photo-container
NHN_STORAGE_URL=https://api-storage.nhncloudservice.com/v1

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

### 사진 업로드

```bash
curl -X POST "http://localhost:8000/photos/" \
  -H "Authorization: Bearer {access_token}" \
  -F "file=@/path/to/photo.jpg" \
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

### 사진 업로드 흐름

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

## 라이선스

MIT License
