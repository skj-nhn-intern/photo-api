# 환경 모드 설정 가이드

## 개요

애플리케이션은 두 가지 환경 모드를 지원합니다:
- **DEV**: 개발 환경
- **PRODUCTION**: 프로덕션 환경

## 환경 모드 설정

### 환경 변수로 설정

`.env` 파일 또는 환경 변수로 설정:

```env
ENVIRONMENT=DEV
# 또는
ENVIRONMENT=PRODUCTION
```

### 자동 설정

- **dev 브랜치 배포**: 자동으로 `DEV` 모드로 설정
- **release 브랜치 배포**: 자동으로 `PRODUCTION` 모드로 설정

## 환경별 차이점

### DEV 모드
- `DEBUG=True` (기본값)
- 상세한 에러 메시지 표시
- 개발용 로그 레벨

### PRODUCTION 모드
- `DEBUG=False` (기본값)
- 최소한의 에러 정보만 표시
- 프로덕션용 로그 레벨

## setup.sh 사용 시

환경 변수로 모드를 지정할 수 있습니다:

```bash
# DEV 모드로 설치
ENVIRONMENT=DEV sudo ./setup.sh

# PRODUCTION 모드로 설치
ENVIRONMENT=PRODUCTION sudo ./setup.sh
```

환경 변수를 지정하지 않으면 기본값은 `DEV`입니다.

## 코드에서 사용

```python
from app.config import get_settings

settings = get_settings()

if settings.is_dev:
    # 개발 환경 로직
    pass

if settings.is_production:
    # 프로덕션 환경 로직
    pass
```

## GitHub Actions 자동 설정

GitHub Actions 워크플로우가 자동으로 환경 모드를 설정합니다:

- **dev 브랜치 또는 태그**: `ENVIRONMENT=DEV`
- **release 브랜치**: `ENVIRONMENT=PRODUCTION`

각 환경에 맞는 `.env.template` 파일이 배포 패키지에 포함됩니다.
