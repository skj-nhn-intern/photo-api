# 메모리 최적화 가이드

이 문서는 Photo API 시스템의 메모리 사용량을 최적화하기 위한 설정과 권장사항을 설명합니다.

## 최적화 개요

4vCPU 8GB RAM 환경을 기준으로 메모리 사용량을 최적화했습니다.

### 예상 메모리 사용량

```
- Photo API (4 workers):     ~1.2GB
- 동시 연결 (2000):          ~3GB
- DB 연결 풀 (70):           ~140MB
- Promtail:                  ~100-200MB
- Python/OS:                 ~500MB
─────────────────────────────
총합:                        ~5GB (안전 마진 포함)
```

## Promtail 메모리 최적화

### 1. 배치 크기 감소

**변경 전:**
```yaml
batchsize: 1048576  # 1MB
```

**변경 후:**
```yaml
batchsize: 524288   # 512KB (50% 감소)
```

**효과:** 메모리 버퍼 사용량 50% 감소

### 2. 배치 대기 시간 증가

**변경 전:**
```yaml
batchwait: 1s
```

**변경 후:**
```yaml
batchwait: 2s
```

**효과:** 더 많은 로그를 모아서 전송하여 네트워크 오버헤드 감소, 메모리 효율 향상

### 3. Journal 최대 나이 감소

**변경 전:**
```yaml
max_age: 12h
```

**변경 후:**
```yaml
max_age: 6h
```

**효과:** 메모리에 유지하는 journal 로그 기간 50% 감소

### 4. systemd 메모리 제한

**추가된 설정:**
```ini
MemoryMax=512M
MemoryHigh=400M
CPUQuota=50%
```

**효과:** Promtail이 메모리를 과도하게 사용하는 것을 방지

## Python 애플리케이션 메모리 최적화

### 1. NHN Logger 큐 크기 감소

**변경 전:**
```python
MAX_QUEUE_SIZE = 10000
BATCH_SIZE = 100
FLUSH_INTERVAL = 5.0
```

**변경 후:**
```python
MAX_QUEUE_SIZE = 5000      # 50% 감소
BATCH_SIZE = 200           # 2배 증가 (더 적은 배치 전송)
FLUSH_INTERVAL = 10.0      # 2배 증가 (더 많은 로그를 모아서 전송)
```

**효과:**
- 큐 메모리 사용량 50% 감소
- 배치 전송 효율 향상으로 네트워크 오버헤드 감소

### 2. 로그 파일 크기 제한

**변경 전:**
```python
maxBytes=10 * 1024 * 1024  # 10MB
backupCount=5
```

**변경 후:**
```python
maxBytes=5 * 1024 * 1024   # 5MB
backupCount=3
```

**효과:**
- 디스크 사용량 감소 (최대 50MB → 20MB)
- 메모리 매핑 파일 크기 감소

### 3. systemd 메모리 제한

**추가된 설정:**
```ini
MemoryMax=6G
MemoryHigh=5G
CPUQuota=300%
```

**효과:** Photo API가 메모리를 과도하게 사용하는 것을 방지

## 모니터링

### Promtail 메모리 사용량 확인

```bash
# systemd 상태 확인
systemctl status promtail

# 메모리 사용량 확인
systemd-cgtop | grep promtail

# 또는
ps aux | grep promtail
```

### Photo API 메모리 사용량 확인

```bash
# systemd 상태 확인
systemctl status photo-api

# 메모리 사용량 확인
systemd-cgtop | grep photo-api

# 또는
ps aux | grep uvicorn
```

### Prometheus 메트릭

다음 메트릭으로 메모리 사용량을 모니터링할 수 있습니다:

```promql
# Promtail 메모리 사용량 (systemd에서 제공)
container_memory_usage_bytes{container="promtail"}

# Photo API 메모리 사용량
container_memory_usage_bytes{container="photo-api"}

# NHN Logger 큐 크기
photo_api_log_queue_size
```

## 추가 최적화 권장사항

### 1. 로그 레벨 조정

프로덕션 환경에서는 불필요한 로그를 줄여 메모리 사용량을 감소시킬 수 있습니다:

```python
# 환경변수로 로그 레벨 설정
LOG_LEVEL=WARNING  # INFO 대신 WARNING 사용
```

### 2. 메트릭 수집 최적화

불필요한 메트릭을 제거하거나 수집 주기를 조정:

```python
# business_metrics_loop 주기 조정 (기본 60초)
PROMETHEUS_BUSINESS_METRICS_INTERVAL=120  # 2분으로 증가
```

### 3. 데이터베이스 연결 풀 최적화

연결 풀 크기를 실제 사용량에 맞게 조정:

```bash
# 환경변수로 조정
DATABASE_POOL_SIZE=15        # 기본값 20에서 감소
DATABASE_MAX_OVERFLOW=30     # 기본값 50에서 감소
```

### 4. 로그 로테이션 자동화

로그 파일이 자동으로 로테이션되도록 설정 (이미 구현됨):

- `app.log`: 5MB 초과 시 로테이션, 최대 3개 백업
- `error.log`: 5MB 초과 시 로테이션, 최대 3개 백업

## 트러블슈팅

### 문제: Promtail이 메모리를 과도하게 사용

**증상:** `systemd-cgtop`에서 Promtail 메모리 사용량이 512MB를 초과

**해결:**
1. `MemoryMax` 설정 확인
2. 배치 크기 추가 감소 (`batchsize: 262144` - 256KB)
3. 로그 레벨을 `warn`으로 유지

### 문제: Photo API가 메모리를 과도하게 사용

**증상:** `systemd-cgtop`에서 Photo API 메모리 사용량이 6GB를 초과

**해결:**
1. Workers 수 감소 (`UVICORN_WORKERS=2`)
2. 동시 연결 수 감소 (`UVICORN_LIMIT_CONCURRENCY=1000`)
3. DB 연결 풀 크기 감소
4. NHN Logger 큐 크기 추가 감소 (`MAX_QUEUE_SIZE=3000`)

### 문제: 로그 파일이 너무 빨리 로테이션됨

**증상:** 로그 파일이 자주 로테이션되어 디스크 공간 부족

**해결:**
1. 로그 레벨 조정 (불필요한 로그 제거)
2. 로그 파일 크기 증가 (`maxBytes=10 * 1024 * 1024`)
3. 백업 파일 수 증가 (`backupCount=5`)

## 참고 자료

- [Promtail Configuration](https://grafana.com/docs/loki/latest/clients/promtail/configuration/)
- [systemd Resource Control](https://www.freedesktop.org/software/systemd/man/systemd.resource-control.html)
- [Python Memory Management](https://docs.python.org/3/c-api/memory.html)
