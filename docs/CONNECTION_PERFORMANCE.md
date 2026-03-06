# Connection 처리량 최적화 가이드

이 문서는 Photo API의 connection 처리량을 향상시키기 위한 설정 가이드입니다.

## 주요 설정 항목

### 1. 데이터베이스 연결 풀 설정

데이터베이스 연결 풀 크기를 조정하여 동시 DB 연결 수를 늘릴 수 있습니다.

**환경변수 설정:**
```bash
# 기본 연결 수 (pool_size)
DATABASE_POOL_SIZE=20          # 기본값: 10

# 추가 연결 수 (max_overflow, 총 연결 = pool_size + max_overflow)
DATABASE_MAX_OVERFLOW=50        # 기본값: 30

# 연결 대기 타임아웃 (초)
DATABASE_POOL_TIMEOUT=30        # 기본값: 30

# 연결 재사용 시간 (초)
DATABASE_POOL_RECYCLE=1800      # 기본값: 1800
```

**권장 설정:**
- **소규모 (동시 사용자 < 100)**: `DATABASE_POOL_SIZE=10`, `DATABASE_MAX_OVERFLOW=30` (총 40개 연결)
- **중규모 (동시 사용자 100-500)**: `DATABASE_POOL_SIZE=20`, `DATABASE_MAX_OVERFLOW=50` (총 70개 연결)
- **대규모 (동시 사용자 500+)**: `DATABASE_POOL_SIZE=50`, `DATABASE_MAX_OVERFLOW=100` (총 150개 연결)

**주의사항:**
- DB 서버의 `max_connections` 설정보다 작게 설정해야 합니다
- PostgreSQL 기본값: 100, MySQL 기본값: 151
- 너무 크게 설정하면 DB 서버 부하가 증가할 수 있습니다

### 2. Uvicorn 서버 설정

Uvicorn의 동시 연결 수와 worker 수를 조정합니다.

**환경변수 설정:**
```bash
# Worker processes 수 (멀티프로세싱)
UVICORN_WORKERS=4              # 기본값: 1 (단일 프로세스)

# 최대 동시 연결 수
UVICORN_LIMIT_CONCURRENCY=2000 # 기본값: 1000

# Worker당 최대 요청 수 (메모리 누수 방지)
UVICORN_LIMIT_MAX_REQUESTS=10000 # 기본값: 10000

# Keep-alive 타임아웃 (초)
UVICORN_TIMEOUT_KEEP_ALIVE=5   # 기본값: 5
```

**권장 설정:**

**단일 서버 (4코어 CPU):**
```bash
UVICORN_WORKERS=4
UVICORN_LIMIT_CONCURRENCY=2000
UVICORN_LIMIT_MAX_REQUESTS=10000
```

**단일 서버 (8코어 CPU):**
```bash
UVICORN_WORKERS=8
UVICORN_LIMIT_CONCURRENCY=4000
UVICORN_LIMIT_MAX_REQUESTS=10000
```

**주의사항:**
- `UVICORN_WORKERS`는 CPU 코어 수와 동일하게 설정하는 것이 일반적입니다
- Workers 수가 많을수록 메모리 사용량이 증가합니다
- `UVICORN_LIMIT_CONCURRENCY`는 서버 메모리와 네트워크 대역폭을 고려하여 설정합니다

### 3. 운영체제 레벨 설정

**파일 디스크립터 제한 증가:**
```bash
# 현재 제한 확인
ulimit -n

# 임시 증가 (세션 종료 시 초기화)
ulimit -n 65536

# 영구 설정 (systemd 서비스)
# /etc/systemd/system/photo-api.service에 추가:
[Service]
LimitNOFILE=65536
```

**네트워크 설정 최적화:**
```bash
# /etc/sysctl.conf에 추가
net.core.somaxconn = 2048
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.ip_local_port_range = 10000 65535

# 적용
sudo sysctl -p
```

## 설정 적용 방법

### 1. 환경변수 설정

`.env` 파일 또는 systemd `EnvironmentFile`에 설정 추가:

```bash
# .env 파일 예시
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=50
UVICORN_WORKERS=4
UVICORN_LIMIT_CONCURRENCY=2000
```

### 2. systemd 서비스 재시작

```bash
sudo systemctl daemon-reload
sudo systemctl restart photo-api
```

### 3. 설정 확인

```bash
# 서비스 상태 확인
sudo systemctl status photo-api

# 로그 확인
sudo journalctl -u photo-api -f

# 메트릭 확인 (Prometheus)
curl http://localhost:8000/metrics | grep -E "(db_pool|uvicorn)"
```

## 모니터링

### 1. 데이터베이스 연결 풀 모니터링

Prometheus 메트릭:
- `photo_api_db_pool_active_connections`: 활성 DB 연결 수
- `photo_api_db_pool_waiting_requests`: 연결 대기 중인 요청 수

### 2. Uvicorn 연결 모니터링

- `uvicorn_connections_active`: 활성 연결 수
- `uvicorn_connections_accepted`: 수락된 총 연결 수

### 3. 성능 지표 확인

- 연결 대기 시간이 길어지면 `DATABASE_POOL_SIZE` 또는 `DATABASE_MAX_OVERFLOW` 증가
- 연결 거부가 발생하면 `UVICORN_LIMIT_CONCURRENCY` 증가
- CPU 사용률이 낮으면 `UVICORN_WORKERS` 증가 고려

## DB 연결 장애 대응 (Circuit Breaker)

DB 연결 대기 시간이 길어져 타임아웃이 발생하면 전면 장애로 이어질 수 있습니다.
이를 방지하기 위해 **Circuit Breaker 패턴**을 적용했습니다.

### Circuit Breaker 동작 방식

1. **CLOSED 상태 (정상)**: 모든 DB 연결 요청 허용
2. **OPEN 상태 (장애)**: DB 연결 실패가 연속으로 발생하면 Circuit Breaker가 OPEN되어 즉시 실패 반환
   - 타임아웃 전에 빠르게 실패하여 전면 장애 방지
   - API는 즉시 응답하여 리소스 낭비 방지
3. **HALF_OPEN 상태 (복구 시도)**: 일정 시간 후 제한적으로 요청 허용하여 복구 확인

### 설정

```bash
# Circuit Breaker 활성화 (기본: true)
DATABASE_CIRCUIT_BREAKER_ENABLED=true

# 연속 실패 횟수 (기본: 5)
# 이 횟수만큼 연속 실패하면 OPEN 상태로 전이
DATABASE_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5

# OPEN 상태 유지 시간 (초, 기본: 30)
# 이 시간 후 HALF_OPEN 상태로 전이하여 복구 시도
DATABASE_CIRCUIT_BREAKER_TIMEOUT=30.0
```

### 모니터링

다음 메트릭으로 DB 연결 상태를 모니터링할 수 있습니다:

- `photo_api_db_pool_wait_duration_seconds`: 연결 풀 대기 시간
- `photo_api_db_pool_timeout_total`: 연결 타임아웃 발생 횟수
- `photo_api_circuit_breaker_state{service="database"}`: Circuit Breaker 상태 (0=CLOSED, 1=OPEN, 2=HALF_OPEN)
- `photo_api_circuit_breaker_requests_total{service="database",status="rejected"}`: Circuit Breaker에 의해 거부된 요청 수

### 장애 시나리오

**시나리오 1: DB 서버 다운**
- DB 연결 시도 → 실패
- 5번 연속 실패 → Circuit Breaker OPEN
- 이후 요청은 즉시 `ConnectionError` 반환 (타임아웃 대기 없음)
- 30초 후 HALF_OPEN으로 전이하여 복구 시도

**시나리오 2: 연결 풀 고갈**
- 연결 풀에서 연결 획득 대기 → 타임아웃
- 타임아웃 발생 → Circuit Breaker 실패 카운트 증가
- 5번 연속 실패 → Circuit Breaker OPEN
- 이후 요청은 즉시 실패하여 리소스 낭비 방지

### 장점

1. **빠른 실패 (Fail-Fast)**: 타임아웃 대기 없이 즉시 실패하여 API 응답 시간 단축
2. **리소스 보호**: DB 연결 대기로 인한 스레드/메모리 낭비 방지
3. **장애 격리**: DB 장애가 전체 시스템으로 전파되는 것을 방지
4. **자동 복구**: DB가 복구되면 자동으로 정상 상태로 전이

## 트러블슈팅

### 문제: "Too many connections" 에러

**원인:** DB 연결 풀 크기가 DB 서버의 `max_connections`를 초과

**해결:**
1. DB 서버의 `max_connections` 확인
2. `DATABASE_POOL_SIZE + DATABASE_MAX_OVERFLOW`가 `max_connections`보다 작도록 조정

### 문제: 연결 타임아웃

**원인:** `DATABASE_POOL_TIMEOUT`이 너무 짧거나 연결 풀이 부족

**해결:**
1. `DATABASE_POOL_TIMEOUT` 증가 (예: 60초)
2. `DATABASE_POOL_SIZE` 또는 `DATABASE_MAX_OVERFLOW` 증가

### 문제: 메모리 부족

**원인:** `UVICORN_WORKERS` 또는 `UVICORN_LIMIT_CONCURRENCY`가 너무 큼

**해결:**
1. Workers 수 감소
2. `UVICORN_LIMIT_CONCURRENCY` 감소
3. 서버 메모리 증설

### 문제: Circuit Breaker가 계속 OPEN 상태

**원인:** DB 서버가 계속 다운되어 있거나 연결 풀이 부족

**해결:**
1. DB 서버 상태 확인
2. DB 연결 풀 크기 확인 (`DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`)
3. DB 서버의 `max_connections` 확인
4. Circuit Breaker 타임아웃 증가 (`DATABASE_CIRCUIT_BREAKER_TIMEOUT`)

### 문제: DB 연결 대기 시간이 길어짐

**원인:** 연결 풀 크기가 부족하거나 DB 서버 부하

**해결:**
1. `photo_api_db_pool_wait_duration_seconds` 메트릭 확인
2. 연결 풀 크기 증가 (`DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`)
3. DB 서버 성능 확인
4. Circuit Breaker가 활성화되어 있는지 확인 (대기 시간 단축)

## 참고 자료

- [SQLAlchemy Connection Pooling](https://docs.sqlalchemy.org/en/20/core/pooling.html)
- [Uvicorn Settings](https://www.uvicorn.org/settings/)
- [FastAPI Performance](https://fastapi.tiangolo.com/deployment/server-workers/)
