# VM Autoscaling 환경 안정성 가이드

## 개요

이 문서는 Photo API를 VM Autoscaling 환경에서 안정적으로 운영하기 위한 가이드입니다.

**Autoscaling 환경 특성**:
- 여러 인스턴스가 동시에 실행
- 인스턴스가 동적으로 추가/제거됨
- 로드밸런서가 트래픽을 분산
- Health check 기반으로 인스턴스 상태 관리

---

## 1. Stateless 설계 확인 ✅

### 현재 상태: Stateless 설계 준수

**확인 사항**:

1. **메모리 기반 상태**:
   - ✅ Object Storage 토큰 캐시: 인스턴스별 독립적 (각 인스턴스가 자체 토큰 가져옴)
   - ✅ CDN 토큰 캐시: 인스턴스별 독립적 (성능 최적화용, 공유 불필요)
   - ✅ 로그 큐: 인스턴스별 독립적 (각 인스턴스가 자체 로그 전송)
   - ✅ Rate limiting: 제거됨 (인프라 레벨에서 처리)

2. **세션/상태 저장**:
   - ✅ JWT 기반 인증 (Stateless)
   - ✅ 모든 상태는 DB 또는 외부 저장소에 저장
   - ✅ 파일은 Object Storage에 저장

**결론**: Autoscaling 환경에 적합한 Stateless 설계 ✅

---

## 2. Health Check 최적화

### 2.1 현재 구현

```python
GET /health
- DB 연결 확인 (타임아웃 2초)
- Object Storage 토큰 확인 (선택적)
- 인스턴스 정보 포함
- 응답 시간: 2초 이내
```

### 2.2 로드밸런서 설정

**권장 설정**:
- **Health check path**: `/health`
- **Health check interval**: 30초
- **Health check timeout**: 5초
- **Healthy threshold**: 2회 연속 성공
- **Unhealthy threshold**: 3회 연속 실패
- **Grace period**: 60초 (Graceful shutdown 시간)

**Nginx 설정 예시**:
```nginx
upstream photo_api_backend {
    # Health check 기반 로드밸런싱
    server 10.0.1.10:8000 max_fails=3 fail_timeout=10s;
    server 10.0.1.11:8000 max_fails=3 fail_timeout=10s;
    server 10.0.1.12:8000 max_fails=3 fail_timeout=10s;
    
    keepalive 32;
}

server {
    # Health check (빠른 응답 필요)
    location /health {
        proxy_pass http://photo_api_backend;
        proxy_connect_timeout 3s;
        proxy_read_timeout 3s;
        access_log off;  # Health check 로그 제외
    }
    
    # API 엔드포인트
    location /api/ {
        proxy_pass http://photo_api_backend;
        proxy_connect_timeout 10s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

### 2.3 Health Check 주의사항

**❌ 피해야 할 것**:
- Health check에서 무거운 작업 수행 (DB 복잡한 쿼리, 외부 API 호출)
- Health check 타임아웃이 너무 길면 (5초 이상)
- Health check가 너무 자주 실행되면 (10초 이하)

**✅ 권장 사항**:
- 간단한 DB 쿼리만 (SELECT 1)
- 타임아웃 2초 이내
- Health check interval 30초 이상

---

## 3. Graceful Shutdown

### 3.1 Autoscaling 환경에서의 중요성

**시나리오**:
1. Autoscaling 그룹이 인스턴스 종료 결정
2. 로드밸런서가 Health check 실패 감지
3. 새 요청 수락 중지
4. 진행 중인 요청 완료 대기
5. 인스턴스 종료

**현재 구현**:
- ✅ 기본 Graceful shutdown 구현
- ⚠️ 진행 중인 요청 완료 대기 없음

### 3.2 개선 방안

```python
# app/main.py
import signal
import time
from contextlib import asynccontextmanager

# 진행 중인 요청 추적
in_flight_requests = 0
shutdown_event = asyncio.Event()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Graceful shutdown for autoscaling."""
    # Signal handlers
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
    ready.set(0)  # Health check 즉시 실패
    log_info("Shutdown signal received", event="lifecycle")
    
    # 진행 중인 요청 완료 대기 (최대 30초)
    max_wait = 30.0
    start_wait = time.time()
    while time.time() - start_wait < max_wait:
        if in_flight_requests == 0:
            break
        await asyncio.sleep(0.5)
    
    # 백그라운드 작업 종료
    pushgateway_task.cancel()
    await logger_service.stop()
    await close_db()
```

---

## 4. 인스턴스 식별 및 모니터링

### 4.1 인스턴스 식별

**현재 구현**:
- `instance_ip`: 환경 변수 또는 자동 감지
- `node_name`: Prometheus 메트릭 라벨
- 로그에 `instance_ip` 포함

**Health check 응답**:
```json
{
  "status": "healthy",
  "instance": "10.0.1.10",
  "version": "1.0.0",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 4.2 메트릭 수집

**인스턴스별 메트릭**:
- Prometheus에서 `instance` 또는 `node` 라벨로 필터링
- Grafana에서 인스턴스별 대시보드 구성 가능

**예시 쿼리**:
```promql
# 인스턴스별 요청 수
sum by (instance) (rate(http_requests_total[5m]))

# 인스턴스별 에러율
sum by (instance) (rate(http_requests_total{status=~"5.."}[5m]))
/
sum by (instance) (rate(http_requests_total[5m]))
```

---

## 5. Autoscaling 그룹 설정

### 5.1 권장 설정

**Health Check**:
- Type: HTTP
- Path: `/health`
- Port: 8000
- Interval: 30초
- Timeout: 5초
- Healthy threshold: 2회
- Unhealthy threshold: 3회

**Scaling Policy**:
- Scale up: CPU > 70% 지속 5분
- Scale down: CPU < 30% 지속 10분
- Min instances: 2
- Max instances: 10
- Desired capacity: 3

**Grace Period**:
- Instance termination: 60초 (Graceful shutdown 시간)

---

## 6. 문제 해결 가이드

### 6.1 인스턴스가 계속 재시작되는 경우

**원인**:
- Health check가 너무 엄격함
- Health check 타임아웃이 너무 짧음
- DB 연결이 느림

**해결**:
1. Health check 타임아웃 확인 (2초 권장)
2. DB 연결 풀 설정 확인
3. Health check 로그 확인

### 6.2 트래픽이 특정 인스턴스에 집중되는 경우

**원인**:
- 로드밸런서 설정 문제
- Health check가 일부 인스턴스만 실패

**해결**:
1. 로드밸런서 로그 확인
2. 모든 인스턴스의 Health check 상태 확인
3. 로드밸런서 알고리즘 확인 (round-robin 권장)

### 6.3 인스턴스 종료 시 요청이 중단되는 경우

**원인**:
- Graceful shutdown이 완전하지 않음
- 진행 중인 요청 대기 시간 부족

**해결**:
1. Graceful shutdown 구현 확인
2. Grace period 증가 (60초 이상)
3. 진행 중인 요청 추적 구현

---

## 7. 모니터링 체크리스트

### 일일 확인
- [ ] 모든 인스턴스가 Health check 통과하는가?
- [ ] 인스턴스별 트래픽 분산이 균등한가?
- [ ] 인스턴스 재시작 빈도는 정상인가?

### 주간 확인
- [ ] Autoscaling 이벤트 로그 검토
- [ ] 인스턴스별 성능 차이 분석
- [ ] Health check 실패 패턴 분석

### 월간 확인
- [ ] Autoscaling 정책 최적화
- [ ] 인스턴스 크기 조정 검토
- [ ] 비용 최적화

---

## 8. 결론

현재 애플리케이션은 **Autoscaling 환경에 적합한 Stateless 설계**를 따르고 있습니다.

**주요 강점**:
- ✅ Stateless 설계
- ✅ 인스턴스 식별 가능
- ✅ Health check 구현
- ✅ 메트릭 수집

**개선 필요**:
- ⚠️ Health check 타임아웃 최적화 (완료)
- ⚠️ Graceful shutdown 개선 (보고서 참고)
- ⚠️ 로드밸런서 설정 가이드 (문서화 완료)

**다음 단계**:
1. Health check 타임아웃 적용 확인
2. Graceful shutdown 개선 구현
3. 로드밸런서 설정 적용
4. Autoscaling 그룹 설정 검증
