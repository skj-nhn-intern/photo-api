# Circuit Breaker 및 외부 서비스 모니터링 메트릭

## 개요

본 문서는 Photo API의 **Circuit Breaker**와 **외부 서비스(External Service)** 연동에 대한 Prometheus 메트릭 정의, 수집 방식, 대시보드·알림 활용 방법을 정리합니다.

- **Circuit Breaker**: 외부 의존성 장애 시 연쇄 실패를 막고, OPEN/HALF_OPEN/CLOSED 상태 전이를 모니터링합니다.
- **외부 서비스**: NHN Object Storage, NHN CDN, NHN Log 등 HTTP 호출의 요청 수, 성공/실패, 지연 시간을 서비스별로 수집합니다.

**수집 방식**: 앱이 `/metrics`로 노출하는 Prometheus 메트릭. `record_external_request()` 컨텍스트 매니저와 `CircuitBreaker.call()` 내부에서 자동 수집됩니다.

---

## 1. Circuit Breaker 메트릭

### 1.1 메트릭 목록

| 메트릭명 | 타입 | 라벨 | 설명 |
|----------|------|------|------|
| `photo_api_circuit_breaker_state` | Gauge | `service` | 현재 상태 (0=CLOSED, 1=OPEN, 2=HALF_OPEN) |
| `photo_api_circuit_breaker_consecutive_failures` | Gauge | `service` | 현재 연속 실패 횟수 (성공 또는 상태 전이 시 리셋) |
| `photo_api_circuit_breaker_last_state_change_timestamp_seconds` | Gauge | `service` | 마지막 상태 전이 시각(Unix timestamp, 초) |
| `photo_api_circuit_breaker_requests_total` | Counter | `service`, `status` | CB를 거친 요청 수 (status: success \| failure \| rejected) |
| `photo_api_circuit_breaker_failures_total` | Counter | `service`, `exception_type` | 예외 타입별 실패 수 |
| `photo_api_circuit_breaker_state_transitions_total` | Counter | `service`, `from_state`, `to_state` | 상태 전이 횟수 |
| `photo_api_circuit_breaker_call_duration_seconds` | Histogram | `service` | CB를 통한 호출 소요 시간(초) |

### 1.2 상태 전이

- **CLOSED** → 연속 실패가 `failure_threshold` 이상이면 **OPEN**
- **OPEN** → `timeout` 경과 후 **HALF_OPEN**
- **HALF_OPEN** → `success_threshold`만큼 연속 성공하면 **CLOSED**, 한 번이라도 실패하면 **OPEN**

### 1.3 Prometheus 쿼리 예시

```promql
# 서비스별 현재 상태 (0/1/2)
photo_api_circuit_breaker_state

# OPEN 상태인 서비스
photo_api_circuit_breaker_state == 1

# OPEN 유지 시간(초): 현재 시각 - 마지막 전이 시각
time() - photo_api_circuit_breaker_last_state_change_timestamp_seconds

# 5분간 rejected 비율 (서비스별)
sum(rate(photo_api_circuit_breaker_requests_total{status="rejected"}[5m])) by (service)
/
sum(rate(photo_api_circuit_breaker_requests_total[5m])) by (service)
* 100

# 5분간 상태 전이 횟수 (플래핑 탐지)
sum(rate(photo_api_circuit_breaker_state_transitions_total[5m])) by (service) * 60

# 연속 실패 횟수 (임계값 근접 시 경고용)
photo_api_circuit_breaker_consecutive_failures
```

### 1.4 Grafana 패널 제안

- **Row: Circuit Breaker 상태**
  - **Stat**: `photo_api_circuit_breaker_state` — 0/1/2를 CLOSED/OPEN/HALF_OPEN 텍스트로 매핑, 1이면 경고색
  - **Table**: 서비스별 `state`, `consecutive_failures`, `last_state_change` (또는 OPEN 유지 시간)
  - **Time series**: `rate(photo_api_circuit_breaker_requests_total[5m])` by (service, status) — success/failure/rejected 추이
  - **Time series**: `rate(photo_api_circuit_breaker_state_transitions_total[5m])` by (service) — 플래핑 추이

### 1.5 알림 기준 제안

| 알림명 | 조건 | 심각도 | 설명 |
|--------|------|--------|------|
| CircuitBreakerOpen | `photo_api_circuit_breaker_state == 1` for 1m | warning | 해당 서비스가 1분 이상 OPEN |
| CircuitBreakerOpenLong | `photo_api_circuit_breaker_state == 1` for 5m | critical | OPEN이 5분 이상 지속 |
| CircuitBreakerFlapping | `sum(rate(photo_api_circuit_breaker_state_transitions_total[5m])) by (service) * 60 > 5` for 5m | warning | 분당 상태 전이 5회 초과 (플래핑) |
| CircuitBreakerRejectionRateHigh | rejected 비율 > 20% for 2m | critical | 요청의 20% 이상이 CB에 의해 거부됨 |

---

## 2. 외부 서비스 메트릭

**해석상 유의:** 아래 메트릭은 **이 API 서버가 OBS/CDN/Log로 보낸 요청**의 성공·실패·지연만 나타냅니다.  
OBS/CDN **서비스 전체의 가동 상태**를 나타내는 것이 아니며, “이 인스턴스의 외부 의존성(연동) 상태”로 해석해야 합니다.  
서비스 자체 상태는 해당 업체 상태 페이지 또는 별도 프로브로 확인하는 것이 맞습니다.

### 2.1 메트릭 목록

| 메트릭명 | 타입 | 라벨 | 설명 |
|----------|------|------|------|
| `photo_api_external_request_total` | Counter | `service`, `status` | 외부 요청 수 (status: success \| failure) |
| `photo_api_external_request_errors_total` | Counter | `service` | 외부 요청 실패 수 |
| `photo_api_external_request_duration_seconds` | Histogram | `service`, `result` | 요청 소요 시간(초), result: success \| failure |

**적용 서비스**: `record_external_request(service)` 사용처 기준 — `obs_api_server`(OBS), `cdn_api_server`(CDN), `log_api_server`(Log). 요청 주체는 API 서버이므로 이름을 OBS/CDN/Log API server로 명시함.

### 2.2 수집 방식

- **총 요청 수·성공/실패**: `record_external_request(service)` 진입 시 성공이면 `external_request_total{status="success"}`, 예외 시 `external_request_total{status="failure"}` 및 `external_request_errors_total` 증가.
- **지연**: 성공/실패 모두 `external_request_duration_seconds{service, result}`에 기록. 실패 호출도 타임아웃·지연 분석에 활용 가능.

### 2.3 Prometheus 쿼리 예시

```promql
# 서비스별 5분간 요청률 (건/초)
sum(rate(photo_api_external_request_total[5m])) by (service)

# 서비스별 5분간 실패율 (%)
sum(rate(photo_api_external_request_total{status="failure"}[5m])) by (service)
/
sum(rate(photo_api_external_request_total[5m])) by (service)
* 100

# 서비스별 5분간 에러 건수 (분당)
sum(rate(photo_api_external_request_errors_total[5m])) by (service) * 60

# 서비스별 P95 지연(초) — 성공 요청만
histogram_quantile(0.95,
  sum(rate(photo_api_external_request_duration_seconds_bucket{result="success"}[5m])) by (le, service)
)

# 서비스별 P95 지연 — 실패 요청 (타임아웃 등 분석)
histogram_quantile(0.95,
  sum(rate(photo_api_external_request_duration_seconds_bucket{result="failure"}[5m])) by (le, service)
)
```

### 2.4 Grafana 패널 제안

- **Row: 외부 서비스 상태**
  - **Time series**: 서비스별 `rate(photo_api_external_request_total[5m])` by (service, status) — 성공/실패 추이
  - **Stat**: 서비스별 실패율(%) — 임계값 초과 시 경고색
  - **Time series**: 서비스별 P95 지연 (success) — 목표선(예: 2초) 추가
  - **Time series**: `rate(photo_api_external_request_errors_total[5m]) * 60` by (service) — 분당 에러 수

### 2.5 알림 기준 제안

| 알림명 | 조건 | 심각도 | 설명 |
|--------|------|--------|------|
| ExternalServiceErrorRateHigh | 서비스별 실패율 > 10% for 5m | warning | 해당 외부 서비스 실패율 10% 초과 |
| ExternalServiceErrorRateCritical | 서비스별 실패율 > 25% for 2m | critical | 실패율 25% 초과 또는 완전 실패 우려 |
| ExternalServiceLatencyHigh | 서비스별 P95(success) > 5 for 5m | warning | 외부 호출 지연 증가 |
| ExternalServiceErrorsSpike | `rate(photo_api_external_request_errors_total[5m])*60 > 20` for 2m | critical | 분당 에러 20건 초과 |

---

## 3. 대시보드 구성 요약

### 3.1 Circuit Breaker 전용 Row

| 패널 | 시각화 | 쿼리/비고 |
|------|--------|------------|
| CB 상태 | Stat / Gauge | `photo_api_circuit_breaker_state` (0/1/2 → 텍스트) |
| OPEN 유지 시간 | Stat | `time() - photo_api_circuit_breaker_last_state_change_timestamp_seconds` (state==1일 때만) |
| 요청 결과 추이 | Time series | `rate(photo_api_circuit_breaker_requests_total[5m])` by (service, status) |
| Rejected 비율 | Stat | rejected / total * 100 (5m rate) |
| 상태 전이 추이 | Time series | `rate(photo_api_circuit_breaker_state_transitions_total[5m])` by (service) |

### 3.2 외부 서비스 전용 Row

| 패널 | 시각화 | 쿼리/비고 |
|------|--------|------------|
| 요청률·성공/실패 | Time series | `rate(photo_api_external_request_total[5m])` by (service, status) |
| 실패율 | Stat | failure/total * 100 by service |
| P95 지연(성공) | Time series | histogram_quantile(0.95, ... result="success") by (service) |
| 분당 에러 수 | Time series | `rate(photo_api_external_request_errors_total[5m])*60` by (service) |

---

## 4. 알림 규칙 예시 (Prometheus)

```yaml
groups:
  - name: photo_api_circuit_breaker
    interval: 30s
    rules:
      - alert: CircuitBreakerOpen
        expr: photo_api_circuit_breaker_state == 1
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Circuit breaker OPEN"
          description: "서비스 {{ $labels.service }}의 circuit breaker가 1분 이상 OPEN 상태입니다."

      - alert: CircuitBreakerOpenLong
        expr: photo_api_circuit_breaker_state == 1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Circuit breaker OPEN 장시간"
          description: "서비스 {{ $labels.service }}의 circuit breaker가 5분 이상 OPEN 상태입니다."

      - alert: CircuitBreakerRejectionRateHigh
        expr: |
          sum(rate(photo_api_circuit_breaker_requests_total{status="rejected"}[5m])) by (service)
          / sum(rate(photo_api_circuit_breaker_requests_total[5m])) by (service) * 100 > 20
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Circuit breaker 거부율 높음"
          description: "서비스 {{ $labels.service }}의 요청 거부율이 20%를 초과합니다."

  - name: photo_api_external_services
    interval: 30s
    rules:
      - alert: ExternalServiceErrorRateHigh
        expr: |
          sum(rate(photo_api_external_request_total{status="failure"}[5m])) by (service)
          / sum(rate(photo_api_external_request_total[5m])) by (service) * 100 > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "외부 서비스 실패율 높음"
          description: "서비스 {{ $labels.service }}의 실패율이 10%를 초과합니다."

      - alert: ExternalServiceErrorRateCritical
        expr: |
          sum(rate(photo_api_external_request_total{status="failure"}[5m])) by (service)
          / sum(rate(photo_api_external_request_total[5m])) by (service) * 100 > 25
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "외부 서비스 실패율 매우 높음"
          description: "서비스 {{ $labels.service }}의 실패율이 25%를 초과합니다."
```

---

## 5. 관련 문서

- **외부 서비스 요청량 전용 대시보드**: `docs/monitoring/EXTERNAL-SERVICE-DASHBOARD.md` — 요청량은 `photo_api_external_request_total` 사용, `_duration_seconds_bucket` 는 지연용.
- **지표 정의·알림 상세**: 프로젝트 루트 `HA_MONITORING_METRICS.md` (Circuit Breaker·외부 서비스 섹션 포함)
- **대시보드 구성·시각화**: `docs/monitoring/SERVICE-MONITORING-DASHBOARD.md`
- **구현**: `app/utils/circuit_breaker.py`, `app/utils/prometheus_metrics.py` (`record_external_request`)
