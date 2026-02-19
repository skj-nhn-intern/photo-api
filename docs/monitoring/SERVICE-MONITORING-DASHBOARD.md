# 서비스 모니터링 대시보드 가이드

## 개요

본 문서는 Photo API 서비스 모니터링을 위한 **대시보드 구성** 시 참고할 **지표**, **수집 방식**(메트릭/로그), **시각화 유형**(가로축·세로축 형식 포함), 그리고 **수집 이유(운영 관점)**를 정리한 문서입니다.

### 수집 방식 요약

| 방식 | 도구 | 용도 |
|------|------|------|
| **메트릭** | Prometheus | 앱이 `/metrics`로 노출하는 숫자 지표. Prometheus가 주기적으로 스크래핑. 집계·알림·대시보드( Grafana )에 사용. |
| **메트릭 (HTTP)** | FastAPI Instrumentator | `http_requests_total`, `http_request_duration_seconds` 등 HTTP 요청 수·지연 자동 수집. |
| **메트릭 (노드)** | node_exporter | CPU, 메모리, 디스크, 네트워크 등 호스트 지표. Prometheus가 스크래핑. |
| **로그** | 앱 로거 + (선택) Loki | 구조화된 애플리케이션 로그(JSON). 장애 원인 분석, 요청 추적, 감사. 대시보드에서는 Loki 쿼리로 로그 기반 지표/패널 보완 가능. |

- **메트릭**: 실시간·집계·알림에 적합. 대시보드의 주 데이터 소스.
- **로그**: 개별 이벤트·스택 트레이스·상세 맥락. 장애 분석·감사 시 보완.

---

## 1. 가용성·서비스 상태

| 지표 | 타입 | 수집 방식 | 시각화 유형 | 가로축 / 세로축 | 수집 이유 (운영) |
|------|------|-----------|-------------|------------------|-------------------|
| `photo_api_ready` | Gauge | 메트릭 (앱) | Gauge 또는 Stat | — / 0 또는 1 | 서비스가 트래픽 수신 가능 상태인지 판단. 0이면 LB에서 제거·알림으로 즉시 대응. |
| `photo_api_app_info` | Gauge | 메트릭 (앱) | 정보성(라벨) | — | 노드·버전·환경 필터링으로 어떤 인스턴스가 올라왔는지 배포 상태 확인. |
| `count(photo_api_ready == 1)` | — | 메트릭 (쿼리) | Stat | — / 정수 | 정상 인스턴스 수. 스케일/롤링 배포 시 절반 이하로 떨어지면 이상 탐지. |

**로그 보완**: 헬스체크 실패·재시작 시 애플리케이션 로그에서 원인(예: DB 연결 실패) 확인.

---

## 2. 성능 (응답 시간·처리량)

| 지표 | 타입 | 수집 방식 | 시각화 유형 | 가로축 / 세로축 | 수집 이유 (운영) |
|------|------|-----------|-------------|------------------|-------------------|
| `http_request_duration_seconds` | Histogram | 메트릭 (Instrumentator) | Time series | 시간 / 초(sec) | 전체 API 응답 시간 추이. P50/P95/P99로 SLA·병목 판단. |
| `http_requests_total` | Counter | 메트릭 (Instrumentator) | Time series, Stat | 시간 / 건·초당 또는 분당 | 처리량(RPS)·트래픽 패턴. 급증 시 DDoS·캠페인 대응. |
| `photo_api_login_duration_seconds` | Histogram | 메트릭 (앱) | Time series | 시간 / 초(sec) | 로그인 지연. 인증 경험·DB/해싱 병목·공격 시 지연 이상 탐지. |
| `photo_api_image_access_duration_seconds` | Histogram | 메트릭 (앱) | Time series | 시간 / 초(sec) | 이미지 로딩 성능. CDN vs 백엔드 효과·SLA(예: P95 &lt; 2초) 확인. |
| `photo_api_share_link_access_duration_seconds` | Histogram | 메트릭 (앱) | Time series | 시간 / 초(sec) | 공유 링크 페이지 접근 지연. 토큰 검증·DB 쿼리 성능 점검. |
| `photo_api_external_request_duration_seconds` | Histogram | 메트릭 (앱) | Time series | 시간 / 초(sec) | Object Storage·CDN·Log 등 외부 의존성 지연. 장애 시 원인 범위 좁히기. |
| `photo_api_active_sessions` | Gauge | 메트릭 (앱) | Time series, Stat | 시간 / 동시 세션 수 | 동시 부하. 스케일·리소스 계획·과부하 전 알림. |

**시각화 상세 (성능)**  
- **Time series**: 가로축 = 시간, 세로축 = 초(응답 시간) 또는 건/초(처리량). 여러 시리즈는 P50/P95/P99 또는 handler별.  
- **Stat**: 현재(또는 최근 구간) P95, RPS 등 단일 숫자. 임계값 초과 시 색상으로 경고.

---

## 3. 안정성 (에러·예외)

| 지표 | 타입 | 수집 방식 | 시각화 유형 | 가로축 / 세로축 | 수집 이유 (운영) |
|------|------|-----------|-------------|------------------|-------------------|
| `http_requests_total{status=~"5.."}` | Counter | 메트릭 (Instrumentator) | Time series, Stat | 시간 / 건·초당 또는 비율(%) | 5xx 에러율. SLA·장애 감지 및 알림. |
| `photo_api_exceptions_total` | Counter | 메트릭 (앱) | Time series | 시간 / 건·분당 | 미처리 예외. 버그·환경 이슈 조기 발견. |
| `photo_api_db_errors_total` | Counter | 메트릭 (앱) | Time series | 시간 / 건·분당 | DB 연결·트랜잭션 실패. 연결 풀·DB 장애 대응. |
| `photo_api_external_request_errors_total` | Counter | 메트릭 (앱) | Time series (서비스별) | 시간 / 건·분당 | 외부 API 실패. Object Storage·CDN·Log 장애 구분. |
| `photo_api_log_queue_size` | Gauge | 메트릭 (앱, Custom Collector) | Time series, Stat | 시간 / 큐 길이(건) | 로그 백프레셔. 큐 폭주 시 메모리·로그 유실 방지. |

**로그 보완**: 예외·DB/외부 에러 발생 시 로그에서 스택 트레이스·요청 ID로 원인 추적.

---

## 4. 보안 (Rate Limit·공유 링크·이미지 접근)

| 지표 | 타입 | 수집 방식 | 시각화 유형 | 가로축 / 세로축 | 수집 이유 (운영) |
|------|------|-----------|-------------|------------------|-------------------|
| `photo_api_rate_limit_hits_total` | Counter | 메트릭 (앱) | Time series, Bar, Table | 시간 또는 endpoint / 건·분당 | Rate limit 차단 추이. DDoS·악성 IP 탐지 및 정책 조정. |
| `photo_api_rate_limit_requests_total` | Counter | 메트릭 (앱) | Time series | 시간 / 건·분당 (allowed vs blocked) | 차단률(blocked/total). 허용률이 너무 낮으면 정상 사용자 영향 검토. |
| `photo_api_share_link_brute_force_attempts_total` | Counter | 메트릭 (앱) | Time series, Table(IP별) | 시간 또는 client_id / 건·분당 | 무효 토큰 시도. 브루트포스·악성 IP 탐지 및 차단. |
| `photo_api_share_link_access_total` | Counter | 메트릭 (앱) | Time series, Pie | 시간 / 건·분당 (token_status, result별) | 공유 링크 사용·실패·만료 패턴. 보안·UX 균형. |
| `photo_api_share_link_image_access_total` | Counter | 메트릭 (앱) | Time series, Pie | 시간 또는 photo_in_album / 건·분당 | 공유 이미지 접근. photo_in_album=no 비율로 권한 오남용 탐지. |
| `photo_api_image_access_total` | Counter | 메트릭 (앱) | Time series, Stat | 시간 / 건·분당 또는 성공률(%) | 인증 vs 공유 이미지 접근·성공률. SLA·권한 이슈 모니터링. |

**시각화 상세 (보안)**  
- **Table**: client_id(또는 endpoint) × 건수. 상위 N개 IP/엔드포인트로 우선 대응 대상 파악.  
- **Bar**: 가로축 = endpoint 또는 client_id, 세로축 = 건·분당. 어떤 경로·누가 많이 차단됐는지 한눈에.

---

## 5. 업로드·다운로드 (비즈니스·용량)

| 지표 | 타입 | 수집 방식 | 시각화 유형 | 가로축 / 세로축 | 수집 이유 (운영) |
|------|------|-----------|-------------|------------------|-------------------|
| `photo_api_photo_upload_total` | Counter | 메트릭 (앱) | Time series, Stat | 시간 / 건·분당 또는 성공률(%) | 업로드 시도·성공·실패. presigned vs direct 비율·품질 모니터링. |
| `photo_api_photo_upload_file_size_bytes` | Histogram | 메트릭 (앱) | Time series(P50/P95), Bar, Heatmap | 시간 또는 le(크기 구간) / 바이트 또는 건수 | 업로드 파일 크기 분포. 스토리지·대역폭 비용·최대 크기 정책 검토. |
| `photo_api_presigned_url_generation_total` | Counter | 메트릭 (앱) | Stat, Time series | 시간 / 성공률(%) 또는 건·분당 | Presigned URL 발급 실패. 업로드 진입 장애 조기 발견. |
| `photo_api_photo_upload_confirm_total` | Counter | 메트릭 (앱) | Stat, Time series | 시간 / 성공률(%) 또는 건·분당 | 업로드 완료 확인 실패. 실제 저장 실패·타임아웃 대응. |
| `photo_api_image_access_total` | Counter | 메트릭 (앱) | Time series, Stat | 시간 / 건·분당 또는 성공률(%) | 이미지 다운로드(조회) 건수·성공률. SLA·용량 계획. |
| `photo_api_image_access_duration_seconds` | Histogram | 메트릭 (앱) | Time series | 시간 / 초(sec) | 이미지 다운로드 지연. P95 목표(예: 2초) 달성 여부. |

**시각화 상세 (업로드)**  
- **Heatmap**: 가로축 = 시간, 세로축 = 파일 크기 구간(le), 색 = 건수 또는 비율. 시간대별 크기 패턴.  
- **Bar(분포)**: 가로축 = 크기 버킷(1KB~10MB), 세로축 = 건수. 정책(최대 업로드 크기) 적정성 검토.

---

## 6. 리소스 (호스트)

| 지표 | 타입 | 수집 방식 | 시각화 유형 | 가로축 / 세로축 | 수집 이유 (운영) |
|------|------|-----------|-------------|------------------|-------------------|
| `node_cpu_seconds_total` (rate 기반 사용률) | Counter | 메트릭 (node_exporter) | Time series, Stat | 시간 / % | CPU 부하. 스케일 아웃·병목 구간 파악. |
| `node_memory_*` (MemAvailable, MemTotal) | Gauge | 메트릭 (node_exporter) | Time series, Stat | 시간 / % 또는 bytes | 메모리 사용률. OOM·로그 큐 폭주 전 대응. |
| `node_filesystem_avail_bytes` 등 | Gauge | 메트릭 (node_exporter) | Time series, Stat | 시간 / % 또는 bytes | 디스크 사용률. 로그·임시 파일로 디스크 가득 참 방지. |
| `node_network_receive_bytes_total` 등 (rate) | Counter | 메트릭 (node_exporter) | Time series | 시간 / Mbps 또는 bytes/s | 네트워크 트래픽. 대역폭·DDoS 추이 확인. |

---

## 7. 로그 기반 보완 (운영 관점)

| 용도 | 수집 방식 | 시각화 유형 | 수집 이유 (운영) |
|------|-----------|-------------|-------------------|
| 5xx·예외 원인 분석 | 로그 (Loki 등) | 로그 패널, 테이블 | 메시지·스택·request_id로 장애 시 첫 원인 파악. |
| 요청 추적 | 로그 (request_id, duration_ms) | 로그 쿼리·대시보드 변수 | 특정 요청의 경로·지연·에러 연계. |
| 감사·보안 조사 | 로그 (인증·공유 접근 이벤트) | 로그 검색·테이블 | 누가·언제·어떤 리소스 접근했는지 사후 검증. |

로그는 **메트릭 대시보드와 별도 로그 대시보드** 또는 Grafana 로그 패널로 두고, 메트릭에서 이상 감지 시 해당 시간대 로그를 연계해 보는 흐름을 권장합니다.

---

## 8. 시각화 유형·축 형식 요약

| 시각화 유형 | 가로축 | 세로축 | 단위 예시 | 사용 예 |
|-------------|--------|--------|-----------|---------|
| **Time series** | 시간 | 값 | 초, %, 건/분, 건/초 | 응답 시간, 에러율, 처리량, 카운터 추이 |
| **Stat (Big number)** | — | 단일 값 | %, 초, 건 | SLA 요약, 현재 에러율, P95, 인스턴스 수 |
| **Gauge** | — | 범위 내 값 | 0~1, % | ready, 사용률 |
| **Bar chart** | 카테고리(endpoint, le, client_id) | 값 | 건·분당, 건수 | 엔드포인트별 차단, 파일 크기 구간별 건수 |
| **Table** | — | 행=엔티티, 열=지표 | client_id, endpoint, 건수 | 상위 IP·엔드포인트 목록 |
| **Pie / Donut** | — | 비율 | % | token_status·result·photo_in_album 비율 |
| **Heatmap** | 시간 | 버킷(le 등) | 색=건수 또는 비율 | 시간×파일 크기 분포 |

---

## 9. SLA 대시보드 만드는 방법

SLA 대시보드는 **약속한 목표**와 **실제 수치**를 한 화면에서 비교하고, 기간별 달성 여부를 보기 위한 **전용 대시보드**로 구성합니다.

### 9.1 만드는 순서

1. **SLA 목표 정의** — 대시보드 상단에 텍스트 패널로 목표 표를 둡니다.
2. **Row 1: SLA 요약** — Stat 패널 여러 개로 “지금 목표 달성 여부”를 한눈에 표시.
3. **Row 2~4** — 가용성 → 신뢰성(에러율·성공률) → 성능(응답 시간) 순으로 Time series·Stat 추가.
4. **Row 5 (선택)** — 기간별(24h/7d/30d) 에러율·가용성 등 “리포트” 스타일 패널.
5. **Row 6** — SLA 정의 요약 텍스트 패널로 마무리.
6. **Threshold 설정** — 각 Stat·Graph에 목표값(임계값)을 넣고, 초과/미달 시 색상(경고/위험)으로 구분.

### 9.2 Row별 구성 요약

| Row | 목적 | 패널 유형 | 가로축 / 세로축 | 사용 지표 예시 |
|-----|------|-----------|------------------|----------------|
| **1. SLA 요약** | 목표 대비 현재 상태 | Stat (Big number) | — / 단일 값(%, 초) | 가용성, 5xx 에러율, API P95, 로그인·이미지 성공률 |
| **2. 가용성** | 서비스 Up·인스턴스 수 | Gauge, Stat, Time series | 시간 / 0~1 또는 % | `photo_api_ready`, 정상 인스턴스 수, (근사) 가용성 % 추이 |
| **3. 신뢰성** | 5xx·핵심 플로우 성공률 추이 | Time series | 시간 / % | 5xx 에러율, 로그인·업로드 확인·이미지 접근 성공률 |
| **4. 성능** | 응답 시간이 목표 이내인지 | Time series | 시간 / 초(sec) | 전체 API P50/P95/P99, 로그인 P95, 이미지 P95 (+ 목표선) |
| **5. 기간별 달성** | 지난 N일 SLA 달성 여부 | Stat 또는 Table | — / % 또는 건 | 지난 24h/7d/30d 5xx 에러율, (가능하면) 가용성 % |
| **6. SLA 정의** | 이 대시보드의 목표 명시 | 텍스트 패널 | — | 가용성 99.9%, 5xx &lt; 1%, P95 &lt; 3초 등 |

### 9.3 핵심 쿼리 예시 (Prometheus)

- **5xx 에러율 (%)**  
  `sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100`
- **전체 API P95 (초)**  
  `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))`
- **이미지 접근 성공률 (%)**  
  `sum(rate(photo_api_image_access_total{result="success"}[5m])) / sum(rate(photo_api_image_access_total[5m])) * 100`
- **지난 24시간 5xx 에러율 (%)**  
  `sum(increase(http_requests_total{status=~"5.."}[24h])) / sum(increase(http_requests_total[24h])) * 100`

### 9.4 Grafana 설정 권장

- **리프레시**: 1분 (또는 30초).
- **시간 범위**: 기본 최근 24시간, 변수로 7d/30d 선택 가능하게.
- **변수**: SLA 대시보드는 보통 **전체 서비스** 기준. 인스턴스 필터는 상세 대시보드에서 사용.
- **Threshold**: 각 Stat에 목표값 설정 후, 초과 시 경고(노란), 위험(빨강) 색상 지정.

상세 패널별 쿼리·목표값 표·알림 기준은 프로젝트 루트의 **`MONITORING_VISUALIZATION.md`** 에서 **「SLA 대시보드 구조 권장」** 섹션을 참고하세요.

---

## 10. 관련 문서

- **지표 정의·알림 상세**: `HA_MONITORING_METRICS.md`
- **Grafana 패널·쿼리·SLA 대시보드 구조(상세)**: `MONITORING_VISUALIZATION.md`
- **로깅 구조·필드**: `LOGGING_IMPLEMENTATION_SUMMARY.md`
- **Rate limiting 메트릭**: `RATE_LIMITING_IMPLEMENTATION.md`
