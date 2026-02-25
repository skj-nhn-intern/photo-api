# 외부 서비스(External Service) 대시보드 — 요청량 시각화

## 요청량 vs 지연 메트릭

- **요청량(건수·건/초·건/분)** 은 **Counter** `photo_api_external_request_total` 로 시각화합니다.  
  `photo_api_external_request_duration_seconds_bucket` 는 **지연 분포(히스토그램)** 용이라, 트래픽이 적을 때 `rate(..._bucket[5m])` 로는 값이 거의 안 나오거나 시리즈가 비어 있을 수 있습니다.
- **지연(P95 등)** 이 필요할 때만 `photo_api_external_request_duration_seconds` 의 `_bucket` / `_count` 를 사용합니다.

**서비스 라벨**: `obs_api_server`(OBS), `cdn_api_server`(CDN), `log_api_server`(Log)

---

## 대시보드 구성 (Grafana)

**폴더**: Photo API → **External Service** (또는 Service Monitor 하위)

### Row 1: 요청량 (Request Volume)

| 패널 제목 | 시각화 | PromQL | Unit | 비고 |
|-----------|--------|--------|------|------|
| **서비스별 요청률 (건/초)** | Time series | `sum(rate(photo_api_external_request_total[5m])) by (service)` | reqps | 서비스별 초당 요청 수 |
| **서비스·상태별 요청률** | Time series | `sum(rate(photo_api_external_request_total[5m])) by (service, status)` | reqps | success / failure 구분 |
| **서비스별 분당 요청 수** | Time series | `sum(rate(photo_api_external_request_total[5m])) by (service) * 60` | reqm | 건/분 |
| **서비스별 총 요청 수 (1h)** | Stat 또는 Table | `sum(increase(photo_api_external_request_total[1h])) by (service)` | short | 최근 1시간 누적 건수 |

### Row 2: 성공/실패율

| 패널 제목 | 시각화 | PromQL | Unit | 비고 |
|-----------|--------|--------|------|------|
| **서비스별 실패율 (%)** | Stat (또는 Gauge) | `sum(rate(photo_api_external_request_total{status="failure"}[5m])) by (service) / sum(rate(photo_api_external_request_total[5m])) by (service) * 100` | percent (0-100) | 10% 초과 시 경고 권장 |
| **서비스별 성공률 (%)** | Stat | `sum(rate(photo_api_external_request_total{status="success"}[5m])) by (service) / sum(rate(photo_api_external_request_total[5m])) by (service) * 100` | percent (0-100) | |
| **분당 에러 건수 (서비스별)** | Time series | `sum(rate(photo_api_external_request_errors_total[5m])) by (service) * 60` | reqm | |

### Row 3: 지연 (선택)

트래픽이 있어서 샘플이 쌓일 때만 의미 있음. 요청량이 거의 없으면 시리즈가 비어 있을 수 있음.

| 패널 제목 | 시각화 | PromQL | Unit | 비고 |
|-----------|--------|--------|------|------|
| **서비스별 P95 지연(성공)** | Time series | `histogram_quantile(0.95, sum(rate(photo_api_external_request_duration_seconds_bucket{result="success"}[5m])) by (le, service))` | s | |
| **서비스별 요청 수(지연 메트릭 기준)** | Time series | `sum(rate(photo_api_external_request_duration_seconds_count[5m])) by (service)` | reqps | 히스토그램에 기록된 요청률 (요청량 대체 확인용) |

---

## 쿼리 요약

- **요청량(건/초)**: `sum(rate(photo_api_external_request_total[5m])) by (service)` 또는 `by (service, status)`
- **요청량(건/분)**: 위 쿼리 끝에 `* 60`
- **누적 건수(1h)**: `sum(increase(photo_api_external_request_total[1h])) by (service)`
- **실패율**: `sum(rate(...{status="failure"}[5m])) by (service) / sum(rate(...[5m])) by (service) * 100`

`photo_api_external_request_duration_seconds_bucket` 는 **지연 구간별 관측 수**이므로, 요청량만 보고 싶을 때는 반드시 **`photo_api_external_request_total`** 을 사용하세요.
