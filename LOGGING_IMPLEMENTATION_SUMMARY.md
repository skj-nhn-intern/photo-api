# 구조화된 로깅 구현 요약

Photo API에 구조화된 로깅(Structured Logging) 시스템을 성공적으로 구현했습니다.

## 변경 사항

### 1. 핵심 로깅 모듈 업그레이드 (`app/utils/logger.py`)

#### 업그레이드된 `JsonLinesFormatter`
- **필수 필드** 추가:
  - `timestamp`: ISO 8601 UTC 타임스탬프
  - `level`: 로그 레벨 (ERROR, WARN, INFO, DEBUG)
  - `service`: 서비스명 (Photo API)
  - `message`: 로그 메시지

- **인프라 컨텍스트** 자동 추가:
  - `host`: 서버 호스트명/IP
  - `instance_id`: 인스턴스 ID
  - `environment`: 환경 (prod, staging, dev)
  - `region`: 리전 (kr1)
  - `version`: 애플리케이션 버전

- **요청 컨텍스트** 지원:
  - `http_method`, `http_path`, `http_status`
  - `duration_ms`: 처리 시간
  - `client_ip`, `user_agent`
  - `request_id`: 요청 추적 ID

- **오류 컨텍스트** 지원:
  - `error_type`: 예외 클래스명
  - `error_message`: 오류 메시지
  - `stack_trace`: 스택 트레이스
  - `error_code`: 내부 에러 코드
  - `retry_count`: 재시도 횟수
  - `upstream_service`: 외부 서비스명

#### 새로운 헬퍼 함수
```python
log_info()      # INFO 레벨 로깅 (주요 비즈니스 이벤트)
log_warning()   # WARNING 레벨 로깅 (잠재적 문제)
log_error()     # ERROR 레벨 로깅 (즉시 대응 필요)
log_debug()     # DEBUG 레벨 로깅 (디버깅 정보)
log_with_context()  # 모든 컨텍스트 제어 가능한 고급 로깅
```

### 2. 로깅 미들웨어 생성 (`app/middlewares/`)

#### 새로운 파일
- `app/middlewares/__init__.py`: 미들웨어 패키지
- `app/middlewares/logging_middleware.py`: 구조화된 로깅 미들웨어

#### `LoggingMiddleware` 기능
- 모든 HTTP 요청에 자동으로 Request ID 생성/전파
- 요청 컨텍스트 자동 수집 (method, path, status, duration, client_ip, user_agent)
- 로그 레벨 자동 결정:
  - 5xx 에러 → ERROR
  - 4xx 에러 → WARNING
  - 느린 요청 (3초 이상) → WARNING
  - 정상 요청 → 로깅 안 함 (노이즈 최소화)
- 응답 헤더에 Request ID 포함 (클라이언트 추적 가능)

### 3. 메인 애플리케이션 업데이트 (`app/main.py`)

#### 변경 사항
- `LoggingMiddleware` 추가
- 기존 미들웨어 코드 제거 (중복 방지)
- 글로벌 예외 핸들러에 구조화된 로깅 적용
- Lifespan 이벤트에 구조화된 로깅 적용

### 4. 라우터 업데이트 (예시: `app/routers/auth.py`)

#### 변경 사항
- 주요 비즈니스 이벤트에 로깅 추가:
  - 사용자 등록 완료
  - 사용자 로그인 성공/실패
- 에러 및 경고 로깅 추가

### 5. 서비스 레이어 업데이트 (예시: `app/services/nhn_object_storage.py`)

#### 변경 사항
- 외부 API 호출 실패 시 구조화된 로깅:
  - 에러 타입, 에러 코드, upstream_service 포함
  - 재시도 로직에 retry_count 포함
  - HTTP 상태 코드 포함

### 6. 문서화

#### 새로운 문서
- **`STRUCTURED_LOGGING_GUIDE.md`**: 구조화된 로깅 사용 가이드
  - 로그 레벨 전략
  - 로그 포맷 설명
  - 사용 방법 및 예시
  - 모범 사례
  - Loki 쿼리 예시

- **`test_logging.py`**: 로깅 시스템 테스트 스크립트
  - 모든 로그 레벨 테스트
  - JSON 포맷 예시 출력
  - 재시도 로직 시뮬레이션

- **`LOGGING_IMPLEMENTATION_SUMMARY.md`**: 이 파일 (구현 요약)

#### 업데이트된 문서
- **`README.md`**: 로깅 섹션 추가
  - 주요 특징 설명
  - 로그 레벨 전략 테이블
  - 기본 사용법 예시
  - 가이드 문서 링크

## 로그 레벨 전략

| **레벨** | **용도** | **예시** |
|:-------:|:---------|:---------|
| **ERROR** | 즉시 대응 필요한 오류 | DB 연결 실패, 외부 API 장애 |
| **WARN** | 잠재적 문제 | 재시도 발생, 임계치 근접 |
| **INFO** | 주요 비즈니스 이벤트 | 사용자 로그인, 사진 업로드 |
| **DEBUG** | 개발/디버깅용 상세 정보 | 함수 진입/종료, 변수 값 |

## 사용 예시

### 기본 로깅
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

### 외부 API 호출 오류 (재시도 포함)
```python
retry_count = 0
max_retries = 3

while retry_count < max_retries:
    try:
        result = await external_api.call()
        break
    except Exception as e:
        retry_count += 1
        
        if retry_count >= max_retries:
            # 최종 실패 -> ERROR
            log_error(
                "External API call failed after retries",
                error_type=type(e).__name__,
                error_message=str(e),
                error_code="API_001",
                upstream_service="nhn_storage_iam",
                retry_count=retry_count,
                exc_info=True,
            )
            raise
        else:
            # 재시도 중 -> WARNING
            log_warning(
                "External API call failed, retrying",
                error_type=type(e).__name__,
                upstream_service="nhn_storage_iam",
                retry_count=retry_count,
            )
```

### 고급 로깅 (모든 컨텍스트 포함)
```python
from app.utils.logger import log_with_context
import logging

log_with_context(
    logging.INFO,
    "Order completed successfully",
    # 요청 컨텍스트
    http_method="POST",
    http_path="/api/orders",
    http_status=201,
    duration_ms=456.78,
    client_ip="192.168.1.100",
    user_agent="Mozilla/5.0...",
    # 비즈니스 컨텍스트
    event="order_complete",
    order_id=67890,
    amount=150000,
)
```

## JSON 로그 포맷 예시

```json
{
  "timestamp": "2024-01-15T09:23:45.123Z",
  "level": "ERROR",
  "service": "Photo API",
  "message": "Database connection failed",
  "host": "192.168.1.10",
  "instance_id": "i-1234567890",
  "environment": "production",
  "region": "kr1",
  "version": "1.0.0",
  "request_id": "abc123def456",
  "http_method": "POST",
  "http_path": "/api/photos",
  "http_status": 500,
  "duration_ms": 1234.56,
  "client_ip": "203.0.113.1",
  "user_agent": "Mozilla/5.0...",
  "error_type": "DatabaseError",
  "error_message": "Connection refused",
  "error_code": "DB_001",
  "upstream_service": "postgresql",
  "retry_count": 3,
  "stack_trace": "Traceback (most recent call last):...",
  "event": "request"
}
```

## 로그 출력 위치

- **stdout**: 텍스트 포맷 (journald, 콘솔)
- **stderr**: ERROR 레벨만 (텍스트 포맷)
- **`/var/log/photo-api/app.log`**: INFO 이상 (JSON 포맷, Promtail → Loki)
- **`/var/log/photo-api/error.log`**: ERROR만 (JSON 포맷, Promtail → Loki)

## 테스트 방법

### 1. 로깅 시스템 테스트
```bash
cd photo-api
python test_logging.py
```

이 스크립트는:
- 모든 로그 레벨 테스트 (INFO, WARNING, ERROR, DEBUG)
- JSON 포맷 예시 출력
- 재시도 로직 시뮬레이션
- Request ID 생성 확인

### 2. 애플리케이션 실행 후 확인
```bash
# 개발 환경 실행
uvicorn app.main:app --reload

# API 호출
curl http://localhost:8000/api/auth/login -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"wrong"}'

# 로그 확인 (콘솔)
# 로그 파일 확인 (있는 경우)
cat /var/log/photo-api/app.log | jq
```

## 주요 이점

1. **장애 추적 용이**: Request ID로 요청의 모든 로그 추적
2. **분석 및 집계**: JSON 포맷으로 Loki, Elasticsearch 등과 통합
3. **운영 효율성**: 로그 레벨 전략으로 중요한 이벤트만 집중
4. **디버깅 효율**: 풍부한 컨텍스트 정보로 빠른 문제 해결
5. **자동화**: 미들웨어가 HTTP 요청/응답을 자동으로 로깅

## Loki 쿼리 예시

```logql
# 특정 Request ID의 모든 로그
{service="Photo API"} |= "abc123def456"

# ERROR 레벨 로그만 조회
{service="Photo API"} | json | level="ERROR"

# 특정 에러 코드 조회
{service="Photo API"} | json | error_code="DB_001"

# 외부 서비스별 에러 집계
sum by (upstream_service) (rate({service="Photo API"} | json | level="ERROR" [5m]))
```

## 다음 단계 (선택 사항)

1. **메트릭 연동**: Prometheus와 로그 메트릭 연동
2. **알림 설정**: Loki AlertManager로 ERROR 로그 알림
3. **대시보드 구축**: Grafana로 로그 시각화
4. **추가 서비스 적용**: 다른 서비스 레이어에도 구조화된 로깅 확대

## 참고 문서

- [구조화된 로깅 가이드](./STRUCTURED_LOGGING_GUIDE.md): 상세 사용법
- [README.md](./README.md): 프로젝트 개요
- [test_logging.py](./test_logging.py): 테스트 스크립트

## 문의

로깅 시스템 관련 문의사항이나 개선 제안은 개발팀에 문의하세요.
