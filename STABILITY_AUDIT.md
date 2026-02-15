# 애플리케이션 안정성 점검 보고서

## 개요

Photo API 애플리케이션의 안정성을 종합적으로 점검하고 보완 사항을 제시합니다.

**점검 일자**: 2024년
**배포 환경**: VM Autoscaling (다중 인스턴스)
**점검 범위**: 
- 에러 핸들링
- 리소스 관리
- 외부 서비스 의존성
- 타임아웃 설정
- Graceful shutdown
- Health check
- 재시도 로직
- Circuit breaker
- 설정 검증
- **Autoscaling 환경 특화 사항** (인스턴스 간 상태 공유, 로드밸런서 통합, Stateless 설계)

---

## 1. 현재 상태 평가

### ✅ 잘 구현된 부분

1. **에러 핸들링**
   - Global exception handler 구현
   - 구조화된 로깅
   - Request ID 추적
   - Prometheus 메트릭 수집

2. **데이터베이스 관리**
   - 연결 풀링 구현
   - 느린 쿼리 로깅
   - 트랜잭션 롤백 처리
   - pool_pre_ping으로 연결 상태 확인

3. **비동기 처리**
   - 비동기 로깅 큐 (논블로킹)
   - 백그라운드 작업 처리
   - Graceful shutdown 기본 구현

4. **모니터링**
   - Prometheus 메트릭 수집
   - 상세한 로깅
   - 외부 서비스 에러 추적

---

## 2. Autoscaling 환경 특화 점검

### 2.0 Stateless 설계 확인

**현재 상태**: ✅ **Stateless 설계 준수**

**확인 사항**:
1. **메모리 기반 상태**:
   - ✅ Object Storage 토큰 캐시: 인스턴스별 독립적 (각 인스턴스가 자체 토큰 가져옴)
   - ✅ CDN 토큰 캐시: 인스턴스별 독립적 (성능 최적화용, 공유 불필요)
   - ✅ 로그 큐: 인스턴스별 독립적 (각 인스턴스가 자체 로그 전송)
   - ✅ Rate limiting: 제거됨 (인프라 레벨에서 처리)

2. **세션/상태 저장**:
   - ✅ JWT 기반 인증 (Stateless)
   - ✅ DB에 모든 상태 저장
   - ✅ 파일은 Object Storage에 저장

**결론**: Autoscaling 환경에 적합한 Stateless 설계 ✅

---

### 2.0.1 인스턴스 식별

**현재 상태**: ✅ **구현됨**

- `instance_ip`: 환경 변수 또는 자동 감지
- `node_name`: Prometheus 메트릭 라벨
- 로그에 `instance_ip` 포함

**추가 개선 사항**:
- Health check 응답에 인스턴스 정보 포함 (디버깅 용이)

---

## 3. 발견된 문제점 및 보완 사항

### 🔴 Critical (즉시 조치 필요)

#### 3.1 Health Check가 너무 단순함 (Autoscaling 환경에서 중요)

**현재 상태**:
```python
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

**문제점**:
- DB 연결 상태 확인 없음
- 외부 서비스 상태 확인 없음
- 실제 서비스 가용성과 무관

**영향** (Autoscaling 환경에서 더 심각):
- DB 다운 시에도 200 OK 반환
- 로드밸런서가 비정상 인스턴스로 트래픽 전송
- 장애 조기 탐지 불가
- **Autoscaling 시**: 비정상 인스턴스가 계속 트래픽을 받아 장애 확산
- **Health check 실패 시**: 인스턴스가 계속 재시작되어 불안정

**보완 방안**:
```python
@app.get("/health")
async def health_check():
    """Health check with dependency verification."""
    checks = {
        "status": "healthy",
        "database": "unknown",
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    # DB 연결 확인
    try:
        async with get_db_context() as db:
            await db.execute(select(1))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = "unhealthy"
        checks["database_error"] = str(e)[:100]
        return JSONResponse(
            status_code=503,
            content=checks
        )
    
    return checks
```

---

#### 2.2 외부 서비스 호출에 재시도 로직 부족

**현재 상태**:
- `nhn_logger.py`: 재시도 로직 있음 ✅
- `nhn_object_storage.py`: 재시도 로직 없음 ❌
- `nhn_cdn.py`: 재시도 로직 없음 ❌

**문제점**:
- Object Storage 인증 실패 시 즉시 에러
- CDN 토큰 생성 실패 시 즉시 에러
- 일시적 네트워크 오류에 취약

**영향**:
- 일시적 네트워크 오류로 인한 불필요한 실패
- 사용자 경험 저하
- 서비스 가용성 감소

**보완 방안**: 재시도 유틸리티 구현

---

#### 2.3 타임아웃 설정 불일치

**현재 상태**:
- Object Storage 업로드: 60초
- Object Storage 다운로드: 60초
- Object Storage 인증: 30초
- CDN 토큰 생성: 기본값 (무제한?)
- Log 전송: 10초

**문제점**:
- 타임아웃이 하드코딩되어 있음
- 설정으로 변경 불가
- 일관성 없음

**보완 방안**: 설정 파일로 이동

---

### 🟡 High (단기 조치 필요)

#### 3.4 Health Check 응답 시간 최적화 (Autoscaling 환경)

**현재 상태**:
- DB 연결 확인 포함 (느릴 수 있음)
- 타임아웃 설정 없음

**문제점** (Autoscaling 환경):
- Health check가 느리면 로드밸런서가 인스턴스를 비정상으로 판단
- DB 연결 실패 시 Health check가 타임아웃까지 대기
- 인스턴스가 불필요하게 재시작될 수 있음

**보완 방안**:
```python
@router.get("/health")
async def health_check():
    """Health check with timeout protection."""
    checks = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "instance": settings.instance_ip or _node_identity(),  # 인스턴스 식별
        "checks": {}
    }
    
    # DB 체크에 타임아웃 적용
    try:
        async with asyncio.timeout(2.0):  # 최대 2초
            async with get_db_context() as db:
                await db.execute(select(1))
        checks["checks"]["database"] = "healthy"
    except asyncio.TimeoutError:
        checks["checks"]["database"] = "timeout"
        return JSONResponse(status_code=503, content=checks)
    except Exception as e:
        checks["checks"]["database"] = "unhealthy"
        return JSONResponse(status_code=503, content=checks)
    
    return checks
```

---

#### 3.5 Circuit Breaker 패턴 없음

**현재 상태**:
- 외부 서비스 실패 시 계속 재시도
- 장애 전파 가능성

**문제점**:
- Object Storage 장애 시 모든 요청 실패
- CDN 장애 시 모든 이미지 접근 실패
- 리소스 낭비 (실패한 요청 반복)

**보완 방안**: Circuit breaker 구현

---

#### 3.6 Graceful Shutdown 불완전 (Autoscaling 환경에서 중요)

**현재 상태**:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown
    pushgateway_task.cancel()
    await logger_service.stop()
    await close_db()
```

**문제점** (Autoscaling 환경에서 더 심각):
- 진행 중인 요청 대기 없음
- DB 트랜잭션 강제 종료 가능
- 로그 손실 가능
- **Autoscaling 시**: 인스턴스 종료 시 진행 중인 요청이 중단되어 사용자 경험 저하
- **로드밸런서**: Health check 실패 후 즉시 트래픽 차단, 진행 중인 요청은 타임아웃까지 대기

**보완 방안**: 요청 완료 대기 로직 추가

---

#### 3.7 로드밸런서와의 통합 최적화

**현재 상태**:
- Health check 구현됨
- 인스턴스 식별 가능

**Autoscaling 환경 고려사항**:
1. **Health check 빈도**: 너무 자주 체크하면 부하 증가
2. **Health check 타임아웃**: 로드밸런서 설정과 일치 필요
3. **Draining**: 종료 예정 인스턴스는 새 요청 수락 중지

**보완 방안**:
- Health check 응답 시간 최적화 (2초 이내)
- Graceful shutdown 시 Health check가 즉시 실패하도록
- 로드밸런서 설정 가이드 제공

---

#### 3.8 DB 연결 풀 설정 하드코딩

**현재 상태**:
```python
pool_size=5,
max_overflow=10,
pool_timeout=30,
pool_recycle=1800,
```

**문제점**:
- 설정 변경 불가
- 환경별 최적화 어려움
- 트래픽 증가 시 대응 어려움

**보완 방안**: 환경 변수로 설정 가능하게

---

#### 3.9 외부 서비스 실패 시 Fallback 전략 부족

**현재 상태**:
- Object Storage 실패 → 즉시 에러
- CDN 실패 → 백엔드 스트리밍 (일부 구현됨)
- Log 서비스 실패 → 로그 손실 (의도적)

**문제점**:
- Object Storage 다운 시 서비스 완전 중단
- 사용자 경험 저하

**보완 방안**: Fallback 전략 수립

---

### 🟢 Medium (중기 개선)

#### 3.10 Autoscaling 환경에서의 메트릭 수집

**현재 상태**: ✅ **구현됨**
- 인스턴스별 메트릭 수집 (`node_name`, `instance_ip`)
- Pushgateway 지원

**추가 개선 사항**:
- 인스턴스별 메트릭 집계 (Grafana에서 인스턴스별 필터링)
- Autoscaling 이벤트 추적 (인스턴스 시작/종료)

---

#### 3.11 설정 검증 부족

**현재 상태**:
- Pydantic으로 기본 검증
- 비즈니스 로직 검증 없음

**문제점**:
- 잘못된 설정으로 인한 런타임 에러
- 장애 조기 탐지 어려움

**보완 방안**: Startup 시 설정 검증

---

#### 3.12 메모리 누수 가능성 (Autoscaling 환경)

**현재 상태**:
- 로그 큐: `deque(maxlen=10000)` ✅
- CDN 토큰 캐시: 무제한 ❌
- Object Storage 토큰: 메모리 캐시 ✅

**문제점**:
- CDN 토큰 캐시가 무한 증가 가능
- 장기 운영 시 메모리 부족

**보완 방안**: 캐시 크기 제한 및 TTL

---

#### 3.13 에러 메시지 정보 노출

**현재 상태**:
- 일부 에러에서 내부 정보 노출 가능

**문제점**:
- 보안 위험
- 디버깅 정보 노출

**보완 방안**: 프로덕션 환경에서 에러 메시지 일반화

---

## 4. Autoscaling 환경 특화 보완 사항

### 4.1 Health Check 최적화 (Autoscaling 환경)

**문제**: Health check가 느리면 로드밸런서가 인스턴스를 비정상으로 판단

**해결**:
```python
# app/routers/health.py 개선
import asyncio
from app.config import get_settings
from app.utils.prometheus_metrics import _node_identity

settings = get_settings()

@router.get("/health")
async def health_check():
    """Health check optimized for autoscaling."""
    checks = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "instance": settings.instance_ip or _node_identity(),  # 인스턴스 식별
        "version": settings.app_version,
        "checks": {}
    }
    overall_healthy = True
    
    # DB 체크에 타임아웃 적용 (최대 2초)
    try:
        async with asyncio.timeout(2.0):
            async with get_db_context() as db:
                await db.execute(select(1))
        checks["checks"]["database"] = "healthy"
        health_check_status.labels(check="database").set(1)
    except asyncio.TimeoutError:
        checks["checks"]["database"] = "timeout"
        health_check_status.labels(check="database").set(0)
        overall_healthy = False
    except Exception as e:
        checks["checks"]["database"] = "unhealthy"
        checks["checks"]["database_error"] = str(e)[:100]
        health_check_status.labels(check="database").set(0)
        overall_healthy = False
    
    # Object Storage는 선택적 (타임아웃 없이 빠르게 체크)
    try:
        from app.services.nhn_object_storage import get_storage_service
        storage = get_storage_service()
        if storage._token:
            checks["checks"]["object_storage"] = "healthy"
        else:
            checks["checks"]["object_storage"] = "unknown"
    except Exception:
        checks["checks"]["object_storage"] = "unknown"
        # Object Storage는 선택적이므로 전체 상태에 영향 없음
    
    if not overall_healthy:
        checks["status"] = "unhealthy"
        health_check_status.labels(check="overall").set(0)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=checks
        )
    
    health_check_status.labels(check="overall").set(1)
    return checks
```

---

### 4.2 Graceful Shutdown 개선 (Autoscaling 환경)

**문제**: 인스턴스 종료 시 진행 중인 요청이 중단됨

**해결**:
```python
# app/main.py 개선
import signal
from contextlib import asynccontextmanager

# Shutdown 이벤트
shutdown_event = asyncio.Event()
in_flight_requests = 0
shutdown_lock = asyncio.Lock()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan with graceful shutdown for autoscaling."""
    # Signal handlers (SIGTERM, SIGINT)
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: shutdown_event.set())
    
    # Startup
    ready.set(1)
    await init_db()
    logger_service = get_logger_service()
    await logger_service.start()
    pushgateway_task = asyncio.create_task(pushgateway_loop())
    
    yield
    
    # Graceful shutdown
    ready.set(0)  # Health check가 즉시 실패하도록
    log_info("Shutdown signal received, starting graceful shutdown", event="lifecycle")
    
    # 1. 새 요청 수락 중지 (Health check 실패로 로드밸런서가 트래픽 차단)
    # FastAPI가 자동으로 처리 (ready=0으로 health check 실패)
    
    # 2. 진행 중인 요청 완료 대기 (최대 30초)
    max_wait = 30.0
    start_wait = time.time()
    while time.time() - start_wait < max_wait:
        # in_flight_requests는 미들웨어에서 추적 필요
        if in_flight_requests == 0:
            break
        await asyncio.sleep(0.5)
    
    # 3. 백그라운드 작업 종료
    pushgateway_task.cancel()
    try:
        await pushgateway_task
    except asyncio.CancelledError:
        pass
    
    # 4. 로그 플러시
    await logger_service.stop()
    
    # 5. DB 연결 종료
    await close_db()
    
    log_info("Graceful shutdown completed", event="lifecycle")
```

---

### 4.3 로드밸런서 설정 가이드

**Nginx 설정 예시** (Autoscaling 환경):
```nginx
upstream photo_api_backend {
    # Health check 기반 로드밸런싱
    server 10.0.1.10:8000 max_fails=3 fail_timeout=10s;
    server 10.0.1.11:8000 max_fails=3 fail_timeout=10s;
    server 10.0.1.12:8000 max_fails=3 fail_timeout=10s backup;
    
    # Health check 설정
    keepalive 32;
}

server {
    location /health {
        proxy_pass http://photo_api_backend;
        proxy_connect_timeout 3s;  # 빠른 실패
        proxy_read_timeout 3s;
    }
    
    location /api/ {
        proxy_pass http://photo_api_backend;
        proxy_connect_timeout 10s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

**Autoscaling 그룹 설정**:
- Health check type: HTTP
- Health check path: `/health`
- Health check interval: 30초
- Health check timeout: 5초
- Healthy threshold: 2회
- Unhealthy threshold: 3회
- Grace period: 60초 (Graceful shutdown 시간)

---

## 5. 보완 사항 구현

### 3.1 Health Check 개선

```python
# app/routers/health.py
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from datetime import datetime
from sqlalchemy import select
from app.database import get_db_context

router = APIRouter(tags=["Health"])

@router.get("/health")
async def health_check():
    """Comprehensive health check with dependency verification."""
    checks = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }
    overall_healthy = True
    
    # DB 연결 확인
    try:
        async with get_db_context() as db:
            await db.execute(select(1))
        checks["checks"]["database"] = "healthy"
    except Exception as e:
        checks["checks"]["database"] = "unhealthy"
        checks["checks"]["database_error"] = str(e)[:100]
        overall_healthy = False
    
    # 외부 서비스 확인 (선택적, 빠른 체크)
    # Object Storage 인증 토큰 확인
    try:
        from app.services.nhn_object_storage import get_storage_service
        storage = get_storage_service()
        # 토큰이 있으면 유효성 간단 체크
        if storage._token:
            checks["checks"]["object_storage"] = "healthy"
        else:
            checks["checks"]["object_storage"] = "unknown"
    except Exception as e:
        checks["checks"]["object_storage"] = "unhealthy"
        checks["checks"]["object_storage_error"] = str(e)[:100]
        # Object Storage는 선택적이므로 전체 상태에 영향 없음
    
    if not overall_healthy:
        checks["status"] = "unhealthy"
        return JSONResponse(
            status_code=503,
            content=checks
        )
    
    return checks

@router.get("/health/liveness")
async def liveness_check():
    """Simple liveness check (always returns 200 if process is running)."""
    return {"status": "alive"}

@router.get("/health/readiness")
async def readiness_check():
    """Readiness check (same as /health but for Kubernetes)."""
    return await health_check()
```

---

### 3.2 재시도 유틸리티 구현

```python
# app/utils/retry.py
import asyncio
import logging
from typing import Callable, TypeVar, Optional
from functools import wraps

logger = logging.getLogger("app.retry")

T = TypeVar('T')

async def retry_with_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
    *args,
    **kwargs
) -> T:
    """
    Retry a function with exponential backoff.
    
    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        retryable_exceptions: Tuple of exceptions to retry
        *args, **kwargs: Arguments to pass to func
    
    Returns:
        Result of func
    
    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    delay = initial_delay
    
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e
            if attempt < max_retries - 1:
                logger.warning(
                    f"Retry attempt {attempt + 1}/{max_retries} failed: {str(e)[:100]}",
                    extra={"event": "retry", "attempt": attempt + 1, "max_retries": max_retries}
                )
                await asyncio.sleep(delay)
                delay = min(delay * exponential_base, max_delay)
            else:
                logger.error(
                    f"All retry attempts failed: {str(e)[:100]}",
                    extra={"event": "retry", "attempt": attempt + 1, "max_retries": max_retries}
                )
    
    raise last_exception
```

---

### 3.3 Circuit Breaker 구현

```python
# app/utils/circuit_breaker.py
import asyncio
import logging
import time
from enum import Enum
from typing import Callable, TypeVar, Optional
from functools import wraps

logger = logging.getLogger("app.circuit_breaker")

T = TypeVar('T')

class CircuitState(Enum):
    CLOSED = "closed"  # 정상 동작
    OPEN = "open"      # 차단 (실패율 높음)
    HALF_OPEN = "half_open"  # 테스트 중

class CircuitBreaker:
    """
    Circuit breaker pattern implementation.
    
    상태 전이:
    - CLOSED → OPEN: 실패율이 threshold 초과
    - OPEN → HALF_OPEN: timeout 후
    - HALF_OPEN → CLOSED: 성공
    - HALF_OPEN → OPEN: 실패
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 60.0,
        expected_exception: tuple = (Exception,),
    ):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            # 상태 확인
            if self.state == CircuitState.OPEN:
                if time.time() - (self.last_failure_time or 0) >= self.timeout:
                    # Timeout 지나면 HALF_OPEN으로 전이
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    logger.info("Circuit breaker: OPEN → HALF_OPEN")
                else:
                    # 아직 차단 상태
                    raise Exception("Circuit breaker is OPEN")
        
        try:
            # 함수 실행
            result = await func(*args, **kwargs)
            
            # 성공 처리
            async with self._lock:
                if self.state == CircuitState.HALF_OPEN:
                    self.success_count += 1
                    if self.success_count >= self.success_threshold:
                        self.state = CircuitState.CLOSED
                        self.failure_count = 0
                        logger.info("Circuit breaker: HALF_OPEN → CLOSED")
                elif self.state == CircuitState.CLOSED:
                    self.failure_count = 0  # 성공 시 카운터 리셋
            
            return result
            
        except self.expected_exception as e:
            # 실패 처리
            async with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.state == CircuitState.HALF_OPEN:
                    # HALF_OPEN에서 실패 → OPEN
                    self.state = CircuitState.OPEN
                    logger.warning("Circuit breaker: HALF_OPEN → OPEN")
                elif self.state == CircuitState.CLOSED:
                    if self.failure_count >= self.failure_threshold:
                        # CLOSED에서 실패율 초과 → OPEN
                        self.state = CircuitState.OPEN
                        logger.warning(f"Circuit breaker: CLOSED → OPEN (failures: {self.failure_count})")
            
            raise
```

---

### 3.4 타임아웃 설정 추가

```python
# app/config.py에 추가
# HTTP Client Timeouts
http_timeout_connect: float = Field(
    default=10.0,
    description="HTTP connection timeout (seconds)"
)
http_timeout_read: float = Field(
    default=30.0,
    description="HTTP read timeout (seconds)"
)
http_timeout_write: float = Field(
    default=30.0,
    description="HTTP write timeout (seconds)"
)

# External Service Timeouts
storage_auth_timeout: float = Field(
    default=30.0,
    description="Object Storage authentication timeout (seconds)"
)
storage_upload_timeout: float = Field(
    default=60.0,
    description="Object Storage upload timeout (seconds)"
)
storage_download_timeout: float = Field(
    default=60.0,
    description="Object Storage download timeout (seconds)"
)
cdn_timeout: float = Field(
    default=10.0,
    description="CDN API timeout (seconds)"
)
log_service_timeout: float = Field(
    default=10.0,
    description="Log service timeout (seconds)"
)
```

---

### 3.5 Graceful Shutdown 개선

```python
# app/main.py 수정
import signal
from contextlib import asynccontextmanager

shutdown_event = asyncio.Event()

def signal_handler():
    """Handle shutdown signals."""
    shutdown_event.set()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan with graceful shutdown."""
    # Signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    # Startup
    ready.set(1)
    await init_db()
    logger_service = get_logger_service()
    await logger_service.start()
    pushgateway_task = asyncio.create_task(pushgateway_loop())
    
    yield
    
    # Graceful shutdown
    ready.set(0)
    log_info("Shutdown signal received, starting graceful shutdown", event="lifecycle")
    
    # 1. 새 요청 수락 중지 (로드밸런서가 health check 실패 감지)
    # (FastAPI가 자동으로 처리)
    
    # 2. 진행 중인 요청 완료 대기 (선택적, 구현 복잡)
    # await asyncio.sleep(10)  # 최대 10초 대기
    
    # 3. 백그라운드 작업 종료
    pushgateway_task.cancel()
    try:
        await pushgateway_task
    except asyncio.CancelledError:
        pass
    
    # 4. 로그 플러시
    await logger_service.stop()
    
    # 5. DB 연결 종료
    await close_db()
    
    log_info("Graceful shutdown completed", event="lifecycle")
```

---

### 3.6 DB 연결 풀 설정화

```python
# app/config.py에 추가
# Database Connection Pool
db_pool_size: int = Field(
    default=5,
    description="Database connection pool size"
)
db_max_overflow: int = Field(
    default=10,
    description="Database connection pool max overflow"
)
db_pool_timeout: int = Field(
    default=30,
    description="Database connection pool timeout (seconds)"
)
db_pool_recycle: int = Field(
    default=1800,
    description="Database connection pool recycle time (seconds)"
)

# app/database.py 수정
engine = create_async_engine(
    _database_url,
    echo=False,
    poolclass=QueuePool,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,
)
```

---

### 3.7 CDN 토큰 캐시 크기 제한

```python
# app/services/nhn_cdn.py 수정
from collections import OrderedDict
from typing import Optional

class NHNCDNService:
    MAX_CACHE_SIZE = 1000  # 최대 캐시 항목 수
    
    def __init__(self):
        self.settings = get_settings()
        # LRU 캐시로 변경
        self._token_cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
    
    def _get_cached_token(self, path: str) -> Optional[str]:
        """Get cached token if valid."""
        if path not in self._token_cache:
            return None
        
        token, expire_time = self._token_cache[path]
        if time.time() < expire_time:
            # Move to end (LRU)
            self._token_cache.move_to_end(path)
            return token
        
        # Expired, remove
        del self._token_cache[path]
        return None
    
    def _cache_token(self, path: str, token: str, expire_time: float):
        """Cache token with LRU eviction."""
        # Remove oldest if cache full
        if len(self._token_cache) >= self.MAX_CACHE_SIZE:
            self._token_cache.popitem(last=False)  # Remove oldest
        
        self._token_cache[path] = (token, expire_time)
        self._token_cache.move_to_end(path)  # Mark as recently used
```

---

## 6. 우선순위별 구현 계획

### Phase 1: Critical (1주일 내)
1. ✅ Health Check 개선
2. ✅ 재시도 유틸리티 구현
3. ✅ 타임아웃 설정화

### Phase 2: High (1개월 내)
4. ✅ Circuit Breaker 구현
5. ✅ Graceful Shutdown 개선
6. ✅ DB 연결 풀 설정화

### Phase 3: Medium (3개월 내)
7. ⚠️ 설정 검증 강화
8. ⚠️ 캐시 크기 제한
9. ⚠️ 에러 메시지 일반화

---

## 7. 모니터링 지표 추가

다음 메트릭을 추가하여 안정성 모니터링 강화:

```python
# app/utils/prometheus_metrics.py에 추가

# Circuit Breaker 상태
circuit_breaker_state = Gauge(
    "photo_api_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["service"],
    registry=REGISTRY,
)

# 재시도 횟수
retry_attempts_total = Counter(
    "photo_api_retry_attempts_total",
    "Total number of retry attempts",
    ["service", "result"],  # result: success | failure
    registry=REGISTRY,
)

# Health check 상태
health_check_status = Gauge(
    "photo_api_health_check_status",
    "Health check status (1=healthy, 0=unhealthy)",
    ["check"],  # check: database | object_storage | overall
    registry=REGISTRY,
)
```

---

## 8. Autoscaling 환경 체크리스트

### Stateless 설계
- [x] 메모리 기반 상태 없음 (Rate limiting 제거됨)
- [x] JWT 기반 인증 (Stateless)
- [x] 모든 상태는 DB 또는 외부 저장소에 저장
- [x] 인스턴스 간 상태 공유 불필요

### Health Check
- [x] DB 연결 상태 확인
- [ ] Health check 타임아웃 설정 (2초 이내)
- [ ] 인스턴스 정보 포함
- [ ] 로드밸런서 설정과 일치

### Graceful Shutdown
- [x] 기본 구현
- [ ] 진행 중인 요청 완료 대기
- [ ] Health check 즉시 실패
- [ ] 최대 대기 시간 설정

### 로드밸런서 통합
- [ ] Health check 빈도 최적화
- [ ] Draining 지원
- [ ] 인스턴스별 메트릭 수집

---

## 9. 체크리스트

### 즉시 확인
- [ ] Health check가 DB 상태를 확인하는가?
- [ ] 외부 서비스 호출에 재시도 로직이 있는가?
- [ ] 타임아웃이 적절히 설정되어 있는가?

### 단기 확인
- [ ] Circuit breaker가 구현되어 있는가?
- [ ] Graceful shutdown이 완전한가?
- [ ] DB 연결 풀이 설정 가능한가?

### 중기 확인
- [ ] 설정 검증이 충분한가?
- [ ] 캐시 크기가 제한되어 있는가?
- [ ] 에러 메시지가 안전한가?

---

## 10. Autoscaling 환경 권장 사항

### 즉시 적용
1. **Health check 타임아웃**: 2초 이내 응답 보장
2. **인스턴스 식별**: Health check 응답에 인스턴스 정보 포함
3. **로드밸런서 설정**: Health check 빈도 및 타임아웃 최적화

### 단기 적용
4. **Graceful shutdown**: 진행 중인 요청 완료 대기
5. **Circuit breaker**: 외부 서비스 장애 시 빠른 실패
6. **재시도 로직**: 일시적 오류에 대한 재시도

### 중기 적용
7. **메트릭 집계**: 인스턴스별 메트릭 분석
8. **Autoscaling 이벤트**: 인스턴스 시작/종료 추적
9. **로드 테스트**: Autoscaling 동작 검증

---

## 11. 결론

현재 애플리케이션은 기본적인 안정성 메커니즘은 갖추고 있으나, 프로덕션 환경에서의 안정성을 위해 다음 사항들이 개선 필요합니다:

1. **Critical**: Health check, 재시도 로직, 타임아웃 설정
2. **High**: Circuit breaker, Graceful shutdown, 설정화
3. **Medium**: 설정 검증, 캐시 관리, 보안

위 보완 사항을 단계적으로 구현하여 고가용성을 확보하시기 바랍니다.
