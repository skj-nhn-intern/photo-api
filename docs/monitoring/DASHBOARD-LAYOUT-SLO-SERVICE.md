# SLO/SLI Overview 및 서비스별 대시보드 배치·시각화 가이드

## 개요

- **SLO/SLI Overview**: 전체 서비스(API + Nginx)의 SLO 달성 여부를 한 화면에서 보는 대시보드.
- **서비스 모니터(Service Monitor)**: 도메인별 상세 대시보드 — **User**(인증), **Album**(앨범), **Image**(사진·업로드·다운로드), **Share**(공유 링크).

Nginx는 API 앞단에서 트래픽을 받으므로, **요청량·응답 코드·업스트림 지연**을 Nginx 메트릭으로 함께 보는 구성을 권장합니다.

---

## 1. 대시보드 폴더 구조 (Grafana 권장)

```
📁 Photo API
├── 📄 SLO/SLI Overview          ← 전체 SLO/SLI 요약
└── 📁 Service Monitor
    ├── 📄 User (Auth)            ← 인증: 로그인·회원가입
    ├── 📄 Album                  ← 앨범 CRUD·앨범-사진
    ├── 📄 Image                  ← 사진 업로드·다운로드(이미지 접근)
    └── 📄 Share                  ← 공유 링크 생성·접근·공유 이미지
```

---

## 2. Nginx 메트릭 정리 (수집 전제)

Nginx 메트릭은 수집 방식에 따라 사용 가능한 지표가 다릅니다.

| 수집 방식 | 사용 가능 지표 | 비고 |
|-----------|----------------|------|
| **nginx-prometheus-exporter** (stub_status) | `nginx_http_requests_total`, `nginx_connections_*` | 경로/업스트림 구분 없음. 전체 요청 수·연결 수만 가능. |
| **nginx-prometheus-exporter** (NGINX Plus API) | 업스트림별 요청 수·응답 시간·상태 코드 | NGINX Plus 필요. |
| **access log 파싱** (nginx-log-exporter, Promtail 등) | 경로별·상태 코드별 요청 수, `upstream_response_time` | 로그 포맷에 `$request_uri` 또는 `$uri`, `$status`, `$upstream_response_time` 포함 필요. |

- **최소 구성(stub_status만 있을 때)**: 아래 문서에서 "Nginx 전체" 패널만 사용 (전체 RPS, 연결 수, API 메트릭으로 경로 구분).
- **로그 기반 또는 Plus 있을 때**: "Nginx: 경로별" 패널을 추가해 `/auth`, `/albums`, `/photos`, `/share` 구간별 요청 수·에러율·응답 시간을 표시.

이 문서에서는 **API 메트릭(handler별)** 은 항상 사용하고, **Nginx** 는 “전체”와 “경로별(가능할 때)” 둘 다 기술합니다.

**데이터 소스·단위 정의**
- **API**: Photo API 앱이 `/metrics`로 노출하는 메트릭. Prometheus가 앱 인스턴스를 스크래핑. (`http_requests_total`, `photo_api_*` 등)
- **Nginx**: Nginx stub_status 또는 로그/Plus 기반 메트릭. (`nginx_http_requests_total`, `nginx_connections_*` 등)
- **소스**: 각 패널이 **API** 메트릭을 쓰는지 **Nginx** 메트릭을 쓰는지 표에 명시. 대부분은 API만 사용하고, Nginx RPS·연결 수·(가능 시) 5xx 비율만 Nginx.
- **단위(Unit)**: Grafana 패널에서 "Standard options" → "Unit"에 넣을 값. 사용한 규칙: `percent (0-100)` = 비율(%), `s` = 초, `short` = 정수(개수·0/1), `reqps` = req/s, `reqm` = 건/분(rate×60), `bytes` = 바이트. 텍스트 패널은 "—".

**로그 레벨(ERROR, WARNING) 비율**
- **각 서비스마다 ERROR/WARNING 비율 패널을 둘 필요는 없습니다.** HTTP 5xx·4xx, 성공률, 지연만으로도 서비스 상태를 판단할 수 있고, 로그 레벨은 보조 지표입니다.
- 넣을 경우 권장:
  - **전체만**: SLO Overview에 "앱 로그 ERROR 건수(또는 비율)" 한 패널. (로그 수집·Loki 등에서 `level=ERROR` 집계.)
  - **서비스별**: User/Album/Image/Share 각 대시보드에 ERROR/WARNING 행을 두지 않고, **로그 전용 대시보드**에서 경로(`http_path`·`handler`)별로 ERROR/WARNING 건수·비율을 보는 구성을 권장. 동일 지표를 서비스 대시보드 4곳에 반복하면 노이즈와 유지보수만 늘어납니다.
- 앱은 현재 로그 레벨별 Prometheus 메트릭을 노출하지 않으므로, 로그 레벨 지표는 **로그 파이프라인(Loki 등)** 기반 쿼리로만 구성 가능합니다.

**Photo API 전송 로그 구조 (Loki 쿼리 기준)**  
앱이 출력하는 JSON 로그 한 줄과, Promtail이 Loki로 보낼 때 쓰는 스트림 라벨을 기준으로 합니다. LogQL에서는 `{job="photo-api"}` 로 스트림을 고른 뒤 `| json` 으로 파싱하면 아래 필드로 필터·집계할 수 있습니다.

| 구분 | 필드(키) | 타입 | 비고 |
|------|----------|------|------|
| **스트림 라벨** (Promtail) | `job` | string | `photo-api` |
| | `app` | string | `photo-api` |
| | `env` | string | `production` 등 |
| | `instance`, `instance_ip` | string | 호스트/인스턴스 식별 |
| **JSON 본문** (앱 `JsonLinesFormatter`) | `timestamp` | string | ISO 8601 |
| | `level` | string | `INFO`, `WARNING`, `ERROR` 등 |
| | `service` | string | `Photo API` |
| | `message` | string | 로그 메시지 |
| | `http_method` | string | 요청 시: `GET`, `POST` 등 |
| | `http_path` | string | 요청 시: `/auth/login`, `/auth/register`, `/albums`, `/photos/...` 등 |
| | `http_status` | number | 요청 시: 200, 401, 500 등 |
| | `duration_ms` | number | 요청 처리 시간(ms) |
| | `client_ip` | string | 클라이언트 IP |
| | `user_agent` | string | User-Agent |
| | `request_id` | string | X-Request-ID |
| | `event` | string | 이벤트 구분: `request`, `auth`, `user_login`, `user_registration`, `photo`, `share`, `storage`, `cdn` 등 |
| | `error_type`, `error_message`, `error_code` | string | 에러 시 |
| | `context` | object | 기타 extra (예: `reason`, `user_id`) |

- **경로 필터**: User 서비스는 `http_path=~"/auth.*"` 또는 `http_path=~".*auth.*"` (prefix 있을 때). Album `/albums.*`, Image `/photos.*`, Share `/share.*`.
- **이벤트 필터**: auth 관련은 `event="user_login"`, `event="user_registration"`, `event="auth"`.
- **로그 소스**: `conf/promtail-config.yaml` — `job_name: photo-api`, `__path__: /var/log/photo-api/app.log`. JSON 한 줄 단위로 전송. Promtail은 **event**, **level**, **path_prefix** 를 스트림 라벨로 추출함(서비스 모니터링용). 상세: `docs/log/2026-02-17-promtail-labels-and-service-monitoring-logs.md`.

**event 횟수 현황 (event별 건수 추이)**  
Loki에서 **event 값별 로그 건수**를 보고 싶을 때:

1. **권장: Promtail에서 `event`를 스트림 라벨로 추출**  
   `conf/promtail-config.yaml`의 `photo-api` / `photo-api-errors` job에 `json.expressions`에 `event: event` 추가, `labels: event: event` 스테이지 추가 후 Promtail 재시작. **이후부터** 아래 한 줄 쿼리로 event별 시리즈가 나옵니다.

   ```logql
   sum by (event) (count_over_time({job="photo-api"}[5m]))
   ```

   - 시각화: **Time series** (Stacked area 또는 Multi-line). Legend에 `{{event}}` 사용.
   - **level** 라벨이 있으면: `sum by (level) (count_over_time({job="photo-api"}[5m]))` 로 ERROR/WARNING/INFO 건수 추이.
   - **path_prefix** 라벨이 있으면: `sum by (event) (count_over_time({job="photo-api", path_prefix="/auth"}[5m]))` 로 User 서비스만 event별 건수.
   - event가 없는 로그는 `event=""` 스트림으로 들어갈 수 있음. 그래프에서 빈 라벨 시리즈만 숨기면 됨.

2. **Promtail 변경 전이거나 라벨을 쓰지 않을 때**  
   event 값마다 쿼리 하나씩 추가 (Legend에 event 이름 지정). 앱에서 쓰는 event 예: `request`, `auth`, `user_login`, `user_registration`, `db`, `cdn`, `storage`, `photo`, `share`, `lifecycle`, `health`, `config`, `circuit_breaker`, `rate_limit`, `nhn_log`, `exception` 등.

---

## 3. SLO/SLI Overview 대시보드

**목적**: 전체 스택( Nginx → API )의 가용성·에러율·지연을 한 화면에서 보고, SLO 달성 여부를 판단.

### 3.1 Row 배치 및 패널 구성

| Row | 제목 | 패널 (좌→우) | 시각화 | 가로축 / 세로축 |
|-----|------|----------------|--------|------------------|
| **1** | **SLO 요약** | 가용성(%), 5xx 에러율(%), API P95(초), 로그인 성공률(%), 이미지 접근 성공률(%) | Stat (Big number) | — / 단일 값. 각 Stat에 목표 Threshold 설정. |
| **2** | **스택 상태** | API 준비(ready), 정상 인스턴스 수, Nginx 연결 수(active 등) | Stat 또는 Gauge | — / 정수 또는 0~1 |
| **3** | **요청 처리량** | Nginx 전체 RPS, API 전체 RPS | Time series (2개 또는 1개에 2시리즈) | 시간 / req/s |
| **4** | **에러율** | Nginx 5xx(또는 4xx+5xx) 비율, API 5xx 비율 | Time series + 목표선(1%) | 시간 / % |
| **5** | **응답 시간** | API P50/P95/P99, (가능 시) Nginx upstream P95 | Time series + 목표선(P95 3초 등) | 시간 / 초(sec) |
| **6** | **도메인별 SLI 요약** | User / Album / Image / Share 각 “성공률 또는 P95” 한 칸씩 | Stat 4개 또는 Table 1개 | — / % 또는 초 |
| **7** | **SLA 목표 정의** | 가용성 99.9%, 5xx &lt; 1%, P95 &lt; 3초 등 | 텍스트 패널 | — |

### 3.2 패널별 넣을 메트릭·쿼리 (구체)

각 Row·패널에 **넣을 메트릭(또는 PromQL)** 을 패널 단위로 정리했습니다. Grafana에서 패널 추가 시 쿼리 필드에 아래를 그대로 사용하면 됩니다.

| Row | 패널 제목 | 사용 메트릭 / PromQL | 시각화 | 소스 | 단위(Unit) | 비고 |
|-----|-----------|----------------------|--------|------|------------|------|
| **1** | 가용성(%) | `(1 - sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))) * 100` | Stat | API | `percent (0-100)` | Threshold 예: 99.9 미만 경고. **메트릭** 기준(아래 참고). |
| **1** | 5xx 에러율(%) | `sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100` | Stat | API | `percent (0-100)` | Threshold: 1% 경고, 5% 위험. **메트릭** 기준(아래 참고). |
| **1** | API P95(초) | `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))` | Stat | API | `s` (초) | Threshold: 3초 초과 경고 |
| **1** | 로그인 성공률(%) | `sum(rate(http_requests_total{handler=~".*login",status=~"2.."}[5m])) / sum(rate(http_requests_total{handler=~".*login"}[5m])) * 100` | Stat | API | `percent (0-100)` | handler는 Instrumentator 라벨(경로) |
| **1** | 이미지 접근 성공률(%) | `sum(rate(photo_api_image_access_total{result="success"}[5m])) / sum(rate(photo_api_image_access_total[5m])) * 100` | Stat | API | `percent (0-100)` | 인증 이미지만(공유는 Share 대시보드) |
| **2** | API 준비(ready) | `avg(photo_api_ready)` | Stat | API | `short` (0 또는 1) | 1=정상, 0=다운 |
| **2** | 정상 인스턴스 수 | `count(photo_api_ready == 1)` | Stat | API | `short` (개수) | 다중 인스턴스 시 |
| **2** | Nginx 연결 수(active) | `nginx_connections_active` 또는 엑스포터 메트릭명 | Stat | Nginx | `short` (개수) | Nginx stub_status 기준 |
| **2** | (선택) 헬스체크 상태 | `photo_api_health_check_status` (check_type별) | Stat | API | `short` (0 또는 1) | 1=통과, 0=실패. health 라우터에서 수집 |
| **2** | (선택) DB 풀 사용 | `photo_api_db_pool_active_connections`, `photo_api_db_pool_waiting_requests` | Stat | API | `short` (개수) | DB 연결 풀 상태 |
| **3** | Nginx RPS | `rate(nginx_http_requests_total[5m])` | Time series | Nginx | `reqps` (req/s) | 메트릭명은 엑스포터에 따름 |
| **3** | API RPS | `sum(rate(http_requests_total[5m]))` | Time series | API | `reqps` (req/s) | Y축: req/s |
| **4** | API 5xx 에러율(%) | `sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100` | Time series | API | `percent (0-100)` | 목표선 1% 상수 추가 |
| **4** | (가능 시) Nginx 5xx 비율 | 로그/Plus 기반 경로별 쿼리 | Time series | Nginx | `percent (0-100)` | stub_status만 있으면 생략 |
| **5** | API P50/P95/P99 | `histogram_quantile(0.50, ...)`, `0.95`, `0.99` — `sum(rate(http_request_duration_seconds_bucket[5m])) by (le)` | Time series | API | `s` (초) | 목표선 P95=3 |
| **6** | User SLI | 로그인 성공률(위와 동일 쿼리) | Stat | API | `percent (0-100)` | |
| **6** | Album SLI | `sum(rate(photo_api_album_operations_total{result="success"}[5m])) / sum(rate(photo_api_album_operations_total[5m])) * 100` | Stat | API | `percent (0-100)` | |
| **6** | Image SLI | 이미지 접근 성공률(위와 동일) 또는 업로드 확인 성공률 | Stat | API | `percent (0-100)` | |
| **6** | Share SLI | `sum(rate(photo_api_share_link_access_total{result="success"}[5m])) / sum(rate(photo_api_share_link_access_total[5m])) * 100` | Stat | API | `percent (0-100)` | |
| **7** | SLA 목표 | (텍스트) 가용성 99.9%, 5xx &lt; 1%, P95 &lt; 3초 등 | Text | — | — | |

**가용성(%)·5xx 에러율(%) — 메트릭 vs 로그**  
- 위 표에서는 **메트릭**(Prometheus `http_requests_total`)으로 계산합니다. 앱이 해당 Counter를 노출하므로 실시간 집계·알림에 적합하고, 로그 수집 부담이 없습니다.  
- **로그**로 같은 지표를 만들고 싶다면 (Loki 등만 있을 때): 요청 로그에 `http_status`(또는 `status`)가 있다면, 구간 내 5xx 건수/전체 건수로 에러율을 구할 수 있습니다. 예 (Loki LogQL):  
  - 5xx 건수: `sum(count_over_time({job="photo-api"} | json | status=~"5.." [5m]))`  
  - 전체 건수: `sum(count_over_time({job="photo-api"} | json [5m]))`  
  → 에러율 = 5xx / 전체 * 100. 가용성(%) = (1 - 5xx/전체) * 100.  
- **정리**: 메트릭이 있으면 메트릭으로 두 지표를 쓰는 것을 권장하고, 로그만 수집하는 환경이면 로그 기반 쿼리로 대체하면 됩니다.

**외부 서비스 라벨 참고**: `photo_api_external_request_errors_total`, `photo_api_external_request_duration_seconds` 의 `service` 라벨은 **`obs_api_server`**(OBS), **`cdn_api_server`**(CDN), **`log_api_server`**(Log) 입니다. 쿼리 시 `{service=~"obs_api_server|cdn_api_server|log_api_server"}` 또는 서비스별로 필터하세요.

### 3.3 시각화·배치 요약

- **Row 1**: 상단 가로 한 줄에 Stat 5개. 각각 Threshold로 목표 미달 시 경고 색.
- **Row 2**: API/Nginx “살아 있음” 지표만 모아서 한 줄.
- **Row 3~5**: Time series는 넓은 폭 1개씩 두고, 여러 쿼리는 같은 그래프에 시리즈 추가 또는 패널 나란히.
- **Row 6**: User / Album / Image / Share 순으로 Stat 4개 또는 1행 4열 Table.
- **Row 7**: 맨 아래 텍스트로 SLA 목표 문구 고정.

---

## 4. Service Monitor — User (Auth) 대시보드

**대상**: `/auth/*` — 로그인, 회원가입, 내 정보(me). Nginx에서 `/auth` 로 들어오는 트래픽 + API handler별 지표.

### 4.1 Row 배치 및 패널

| Row | 제목 | 패널 (좌→우) | 시각화 | 가로축 / 세로축 |
|-----|------|----------------|--------|------------------|
| **1** | **요약** | 로그인 성공률(%), 회원가입 성공률(%), User 서비스 지연 P50/P95/P99(초) | Stat 2개 + 지연 1패널(P50·P95·P99) | — / %, 초 |
| **2** | **요청량** | Nginx: /auth 요청 수(가능 시), API: /auth handler별 요청 수 | Time series | 시간 / req/s 또는 건·분당 |
| **3** | **성공률 추이** | 로그인 2xx 비율, 회원가입 2xx 비율 | Time series | 시간 / % |
| **4** | **지연** | User 서비스(/auth 전체) P50/P95/P99 (`http_request_duration_seconds` handler=~"/auth.*") | Time series | 시간 / 초(sec) |
| **5** | **에러** | /auth 4xx·5xx 건수 또는 비율 (API 기준) | Time series 또는 Bar | 시간 / 건·분당 또는 % |
| **6** | **보안 (client_ip)** | 로그인 실패(401) 상위 IP(가능 시), /auth Rate limit 상위 IP(client_id) | Time series + Table | 시간 / 건·분당, client_id·건수 |
| **7** | **로그 이벤트별 분포 추이** | User 서비스 로그의 `event`별 건수 추이 (user_login, user_registration, auth 등) | Time series (Stacked area 또는 Multi-line) | 시간 / 건·분당 |

**로그 이벤트별 분포 추이**  
앱이 구조화 로그에 남기는 `event` 필드 기준으로, `/auth` 구간 이벤트(user_login, user_registration, auth)별 건수 추이를 보면 로그인·회원가입·인증 실패 등 비율과 트렌드를 한눈에 볼 수 있습니다. 데이터 소스는 **로그(Loki)** 이며, 로그 수집 시 `http_path`, `event`가 파싱되어 있어야 합니다.

**로그 이벤트 LogQL 예시 (전송 로그 구조 기준)**  
스트림은 `job="photo-api"`, 파싱은 `| json`, User 서비스는 `http_path=~"/auth.*"`. 이벤트별로 쿼리 3개 추가하고 Legend만 다르게.

- user_login:  
  `sum(count_over_time({job="photo-api"} | json | http_path=~"/auth.*" | event="user_login" [5m]))`
- user_registration:  
  `sum(count_over_time({job="photo-api"} | json | http_path=~"/auth.*" | event="user_registration" [5m]))`
- auth:  
  `sum(count_over_time({job="photo-api"} | json | http_path=~"/auth.*" | event="auth" [5m]))`

분당 건수로 보려면 `* 12` (5분 구간이면 1분당 약 12개 스텝으로 나누는 식은 아님). 5분 구간 건수 그대로 두거나, 구간을 `[1m]`으로 하고 `sum(count_over_time(... [1m])) * 60` 형태로 1분당 환산할 수 있음.

**"Group by" 변환 오류 (One or more queries failed to return fields)**  
Loki에서 `count_over_time(...)` 같은 쿼리는 **메트릭**(시간+값)만 반환하고, 테이블의 "필드(컬럼)"가 없습니다. Grafana의 "Group by" 변환은 **필드가 있는 결과**(예: 로그 테이블)에만 사용할 수 있어, 메트릭 쿼리 결과에 적용하면 위 오류가 납니다. **해결**: Group by 변환을 쓰지 말고, 이벤트별로 **쿼리를 3개 넣고** 각 쿼리의 Legend를 `user_login`, `user_registration`, `auth`로 두면 같은 패널에 시리즈 3개가 나옵니다. 시각화를 Stacked area로 하면 이벤트별 분포 추이가 됩니다.

**client_ip로 시각화할 부분**  
- **로그인 브루트포스·자격증명 시도**: 특정 IP에서 401이 집중되면 공격 또는 봇 의심. 현재 앱 메트릭에는 “handler·status별”만 있으므로 **IP별** 집계는 (1) 로그(Loki 등)에서 `client_ip`·`status=401`로 그룹핑하거나, (2) 앱에서 `photo_api_login_failures_total{client_id="..."}` 같은 메트릭을 추가해야 함.  
- **Rate limit**: `/auth` 경로에서 rate limit에 걸린 상위 IP는 **메트릭으로 가능**. `photo_api_rate_limit_hits_total`에 `endpoint`, `client_id` 라벨이 있으므로 auth 엔드포인트만 필터해 Table/Time series로 표시하면 됨.

### 4.2 패널별 넣을 메트릭·쿼리 (구체)

| Row | 패널 제목 | 사용 메트릭 / PromQL | 시각화 | 소스 | 단위(Unit) | 비고 |
|-----|-----------|----------------------|--------|------|------------|------|
| **1** | 로그인 성공률(%) | `sum(rate(http_requests_total{handler=~".*login",status=~"2.."}[5m])) / sum(rate(http_requests_total{handler=~".*login"}[5m])) * 100` | Stat | API | `percent (0-100)` | |
| **1** | 회원가입 성공률(%) | `sum(rate(http_requests_total{handler=~".*register",status=~"2.."}[5m])) / sum(rate(http_requests_total{handler=~".*register"}[5m])) * 100` | Stat | API | `percent (0-100)` | register 전용 메트릭 없음 → Instrumentator handler 사용 |
| **1** | User 서비스 P50/P95/P99(초) | 한 패널에 쿼리 3개: P50 `histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket{handler=~"/auth.*"}[5m])) by (le))`, P95 `histogram_quantile(0.95, ...)`, P99 `histogram_quantile(0.99, ...)`. Stat이면 "All values"; Time series면 시리즈 3개. | Stat 또는 Time series | API | `s` (초) | /auth 전체(로그인·회원가입·me 등) 요청 지연. |
| **2** | /auth 요청 수(분당) | `sum(rate(http_requests_total{handler=~"/auth.*"}[5m])) * 60` | Time series | API | `reqm` (건/분) | handler는 앱 라우트 경로(예: /auth/login, /auth/register) |
| **2** | (가능 시) Nginx /auth RPS | 로그 기반 경로별 메트릭 | Time series | Nginx | `reqps` (req/s) | |
| **3** | 로그인 2xx 비율 | 위 로그인 성공률과 동일 쿼리 | Time series | API | `percent (0-100)` | 시간 / % |
| **3** | 회원가입 2xx 비율 | 위 회원가입 성공률과 동일 쿼리 | Time series | API | `percent (0-100)` | 시간 / % |
| **4** | User 서비스 P50/P95/P99 | `histogram_quantile(0.5, sum(rate(http_request_duration_seconds_bucket{handler=~"/auth.*"}[5m])) by (le))` (0.95, 0.99 동일) | Time series | API | `s` (초) | /auth 전체 지연 추이. 로그인만 보려면 `photo_api_login_duration_seconds_bucket` 사용 가능. |
| **5** | /auth 4xx·5xx (분당) | `sum(rate(http_requests_total{handler=~"/auth.*",status=~"4.."}[5m])) * 60`, `status=~"5.."` 별도 시리즈 | Time series 또는 Bar | API | `reqm` (건/분) | |
| **6** | (가능 시) 로그인 401 상위 IP | 로그(Loki): 전송 로그 구조 기준. `{job="photo-api"} \| json \| http_path=~"/auth.*" \| http_status=401` 로 필터 후, Loki에서 client_ip별 집계(쿼리별로 topk 등) 또는 "Logs to Metrics"로 client_ip 라벨 추출 후 Table. 또는 앱에 `photo_api_login_failures_total{client_id}` 추가 시 PromQL. | Table | 로그(Loki) 또는 API | `reqm`, client_ip | JSON 필드 `http_status`, `client_ip` 사용. |
| **6** | /auth Rate limit 상위 IP | `topk(10, sum by (client_id) (rate(photo_api_rate_limit_hits_total{endpoint=~".*auth.*"}[5m])) * 60)` | Time series + Table | API | `reqm` (건/분), client_id | client_id는 IP 주소 일부(개인정보 보호). |
| **7** | 로그 이벤트별 분포 추이 | Loki: 전송 로그 구조 기준. 스트림 `job="photo-api"`, 파싱 `\| json`, User 구간 `http_path=~"/auth.*"`, 이벤트별 쿼리 3개 (Legend: user_login / user_registration / auth). 아래 "로그 이벤트 LogQL 예시" 참고. Group by 변환 사용 금지. | Time series (Stacked area) | 로그(Loki) | 건수(또는 분당 환산) | Group by 변환은 메트릭 결과에는 필드 없어 실패 → 쿼리 여러 개로 시리즈만 추가. |

### 4.3 배치 요약

- 1행: 로그인 성공률·회원가입 성공률 Stat 2개 + **User 서비스 지연 1패널(P50·P95·P99)**. 지연은 `/auth` 전체 요청 기준(`http_request_duration_seconds`). 쿼리 3개 추가 후 Stat이면 "All values", Time series면 시리즈 3개.
- 2~5행: Time series로 추이. 에러는 Bar 또는 Time series 한 개에 4xx/5xx 시리즈.
- 6행(보안): **client_ip(client_id)** 로 로그인 401 상위 IP(로그 또는 전용 메트릭), /auth Rate limit 상위 IP(메트릭 `photo_api_rate_limit_hits_total`). 브루트포스·남용 IP 조기 파악용.
- 7행(로그 이벤트): **로그 이벤트별 분포 추이** — User 서비스 로그에서 `event`(user_login, user_registration, auth)별 건수 추이. 로그(Loki) 기반, Time series(Stacked area 권장)로 이벤트 비율·트렌드 확인.

---

## 5. Service Monitor — Album 대시보드

**대상**: `/albums/*` — 앨범 CRUD, 앨범-사진 추가/삭제, 앨범 공유 링크 생성/조회/삭제.

### 5.1 Row 배치 및 패널

| Row | 제목 | 패널 (좌→우) | 시각화 | 가로축 / 세로축 |
|-----|------|----------------|--------|------------------|
| **1** | **요약** | 앨범 작업 성공률(%), 앨범-사진 작업 성공률(%), /albums 요청 수(분당) | Stat 3개 | — / %, 건·분당 |
| **2** | **요청량** | Nginx: /albums 요청(가능 시), API: handler별 /albums 요청 | Time series | 시간 / req/s 또는 건·분당 |
| **3** | **앨범 작업** | create/update/delete 성공률 또는 건수 (operation, result별) | Time series 또는 Bar | 시간 또는 operation / %, 건수 |
| **4** | **앨범-사진 작업** | add/remove 성공률 또는 건수 | Time series 또는 Bar | 시간 또는 operation / %, 건수 |
| **5** | **에러** | /albums 4xx·5xx (API) | Time series | 시간 / 건·분당 또는 % |

### 5.2 패널별 넣을 메트릭·쿼리 (구체)

| Row | 패널 제목 | 사용 메트릭 / PromQL | 시각화 | 소스 | 단위(Unit) | 비고 |
|-----|-----------|----------------------|--------|------|------------|------|
| **1** | 앨범 작업 성공률(%) | `sum(rate(photo_api_album_operations_total{result="success"}[5m])) / sum(rate(photo_api_album_operations_total[5m])) * 100` | Stat | API | `percent (0-100)` | create/update/delete 합산 |
| **1** | 앨범-사진 작업 성공률(%) | `sum(rate(photo_api_album_photo_operations_total{result="success"}[5m])) / sum(rate(photo_api_album_photo_operations_total[5m])) * 100` | Stat | API | `percent (0-100)` | add/remove 합산 |
| **1** | /albums 요청(분당) | `sum(rate(http_requests_total{handler=~"/albums.*"}[5m])) * 60` | Stat | API | `reqm` (건/분) | |
| **2** | /albums handler별 요청 | `sum by (handler) (rate(http_requests_total{handler=~"/albums.*"}[5m])) * 60` | Time series | API | `reqm` (건/분) | Y축: 건/분 |
| **3** | 앨범 작업 건수(operation별) | `sum by (operation, result) (rate(photo_api_album_operations_total[5m])) * 60` | Time series 또는 Bar | API | `reqm` (건/분) | create/update/delete, success/failure |
| **4** | 앨범-사진 작업 건수(operation별) | `sum by (operation, result) (rate(photo_api_album_photo_operations_total[5m])) * 60` | Time series 또는 Bar | API | `reqm` (건/분) | add/remove, success/failure |
| **5** | /albums 4xx·5xx | `sum(rate(http_requests_total{handler=~"/albums.*",status=~"4.."}[5m])) * 60`, `status=~"5.."` | Time series | API | `reqm` (건/분) | |

**공유 링크 생성**: `photo_api_share_link_creation_total` (result별) — 앨범 대시보드에 “공유 링크 생성 성공률” Stat 하나 추가 가능. 쿼리: `sum(rate(photo_api_share_link_creation_total{result="success"}[5m])) / sum(rate(photo_api_share_link_creation_total[5m])) * 100`.

### 5.3 배치 요약

- Row 1: Stat으로 성공률·처리량.
- Row 2: 트래픽 추이.
- Row 3~4: operation별(create/update/delete, add/remove) 성공률 또는 건수. Bar는 가로축=operation, 세로축=건수 또는 %.

---

## 6. Service Monitor — Image 대시보드

**대상**: `/photos/*` — Presigned URL 발급, 업로드 확인, 직접 업로드, 이미지 조회(`/photos/{id}/image`). 업로드·다운로드 모두 포함.

**가용성 시각화**: Image 대시보드는 **쓰기 가용성**(업로드·Presigned·확인)과 **읽기 가용성**(이미지 접근·다운로드)으로 나눠서 보는 구성을 권장합니다. 쓰기 장애(스토리지·Presigned 실패)와 읽기 장애(이미지 로딩·CDN 실패)의 원인이 다르므로, 요약 행과 패널을 두 블록으로 구분해 두면 장애 시나리오별로 빠르게 원인을 좁힐 수 있습니다.

### 6.1 Row 배치 및 패널

| Row | 제목 | 패널 (좌→우) | 시각화 | 가로축 / 세로축 |
|-----|------|----------------|--------|------------------|
| **1** | **요약 — 쓰기 가용성** | 업로드 성공률(%), Presigned URL 성공률(%), 업로드 확인 성공률(%) | Stat 3개 | — / % |
| **1** | **요약 — 읽기 가용성** | 이미지 접근 성공률(%), 이미지 P95(초) | Stat 2개 | — / %, 초 |
| **2** | **요청량** | Nginx: /photos 요청(가능 시), API: presigned/confirm/image 등 handler별 | Time series | 시간 / req/s 또는 건·분당 |
| **3** | **쓰기: 업로드** | 업로드 시도·성공·실패(presigned vs direct), Presigned 발급·업로드 확인 성공률 | Time series 또는 Bar | 시간 또는 upload_method / 건·분당, % |
| **4** | **읽기: 이미지 접근(다운로드)** | 인증 이미지 접근 건수·성공률, P50/P95/P99 (공유 이미지 제외) | Time series | 시간 / 건·분당, %, 초(sec) |
| **5** | **파일 크기** | 업로드 파일 크기 분포(P50/P95) 또는 버킷별 건수 | Time series 또는 Bar | 시간 또는 le / bytes, 건수 |
| **6** | **에러** | /photos 5xx, 업로드 확인 실패(쓰기), 이미지 접근 거부(읽기) | Time series | 시간 / 건·분당 또는 % |

### 6.2 패널별 넣을 메트릭·쿼리 (구체)

**요약 Row 1**은 쓰기 가용성(Stat 3개)과 읽기 가용성(Stat 2개)을 한 줄에 나란히 두거나, 상단에 "쓰기 가용성" / "읽기 가용성" 라벨을 붙인 두 블록으로 배치하면 됩니다.

| Row | 패널 제목 | 사용 메트릭 / PromQL | 시각화 | 소스 | 단위(Unit) | 비고 |
|-----|-----------|----------------------|--------|------|------------|------|
| **1 (쓰기)** | 업로드 성공률(%) | `sum(rate(photo_api_photo_upload_total{result="success"}[5m])) / sum(rate(photo_api_photo_upload_total[5m])) * 100` | Stat | API | `percent (0-100)` | presigned+direct 합산. **쓰기 가용성** |
| **1 (쓰기)** | Presigned URL 성공률(%) | `sum(rate(photo_api_presigned_url_generation_total{result="success"}[5m])) / sum(rate(photo_api_presigned_url_generation_total[5m])) * 100` | Stat | API | `percent (0-100)` | **쓰기 가용성** |
| **1 (쓰기)** | 업로드 확인 성공률(%) | `sum(rate(photo_api_photo_upload_confirm_total{result="success"}[5m])) / sum(rate(photo_api_photo_upload_confirm_total[5m])) * 100` | Stat | API | `percent (0-100)` | **쓰기 가용성** |
| **1 (읽기)** | 이미지 접근 성공률(%) | `sum(rate(photo_api_image_access_total{result="success"}[5m])) / sum(rate(photo_api_image_access_total[5m])) * 100` | Stat | API | `percent (0-100)` | 인증(authenticated) 기준. **읽기 가용성** |
| **1 (읽기)** | 이미지 P95(초) | `histogram_quantile(0.95, sum(rate(photo_api_image_access_duration_seconds_bucket{result="success"}[5m])) by (le))` | Stat | API | `s` (초) | **읽기 가용성** |
| **2** | /photos 요청(분당) | `sum(rate(http_requests_total{handler=~"/photos.*"}[5m])) * 60` | Time series | API | `reqm` (건/분) | |
| **2** | (선택) handler별 | `sum by (handler) (rate(http_requests_total{handler=~"/photos.*"}[5m])) * 60` | Time series | API | `reqm` (건/분) | presigned-url, confirm, image 등 구분 |
| **3** | 업로드 건수(upload_method, result별) | `sum by (upload_method, result) (rate(photo_api_photo_upload_total[5m])) * 60` | Time series 또는 Bar | API | `reqm` (건/분) | 쓰기 플로우 |
| **3** | 업로드 확인 성공률 추이 | `sum(rate(photo_api_photo_upload_confirm_total{result="success"}[5m])) / sum(rate(photo_api_photo_upload_confirm_total[5m])) * 100` | Time series | API | `percent (0-100)` | 시간 / %. 쓰기 가용성 추이 |
| **4** | 이미지 접근 건수(분당) | `sum(rate(photo_api_image_access_total{access_type="authenticated"}[5m])) * 60` | Time series | API | `reqm` (건/분) | **읽기**. 인증 사용자만. 공유 이미지는 Share 대시보드. |
| **4** | 이미지 P50/P95/P99 | `histogram_quantile(0.5, sum(rate(photo_api_image_access_duration_seconds_bucket{result="success"}[5m])) by (le))` (0.95, 0.99 동일) | Time series | API | `s` (초) | 읽기 지연. Y축: 초(sec) |
| **5** | 업로드 파일 크기 P50/P95 | `histogram_quantile(0.5, sum(rate(photo_api_photo_upload_file_size_bytes_bucket[5m])) by (le, upload_method))`, 0.95 동일 | Time series | API | `bytes` | upload_method별 시리즈 |
| **6** | /photos 5xx(분당) | `sum(rate(http_requests_total{handler=~"/photos.*",status=~"5.."}[5m])) * 60` | Time series | API | `reqm` (건/분) | |
| **6** | 업로드 확인 실패(분당) | `sum(rate(photo_api_photo_upload_confirm_total{result="failure"}[5m])) * 60` | Time series | API | `reqm` (건/분) | 쓰기 에러 |
| **6** | 이미지 접근 거부(분당) | `sum(rate(photo_api_image_access_total{result="denied"}[5m])) * 60` | Time series | API | `reqm` (건/분) | 읽기 에러 |

### 6.3 배치 요약

- **Row 1**: **쓰기 가용성** Stat 3개(업로드 성공률, Presigned URL 성공률, 업로드 확인 성공률) + **읽기 가용성** Stat 2개(이미지 접근 성공률, 이미지 P95). 한 줄에 나란히 두거나 "쓰기 / 읽기" 라벨로 블록 구분.
- Row 2: Nginx + API 요청량.
- **Row 3 (쓰기)**: 업로드 플로우(presigned/direct, confirm 성공률 추이).
- **Row 4 (읽기)**: 이미지 접근(인증만) 건수·성공률·지연(P50/P95/P99). 공유 링크 이미지 조회는 Share 대시보드.
- Row 5: 파일 크기 분포(용량·비용 검토).
- Row 6: 에러 추이 — /photos 5xx, 쓰기(업로드 확인 실패), 읽기(이미지 접근 거부)를 시리즈별로 구분해 표시하면 원인 파악에 유리.

---

## 7. Service Monitor — Share 대시보드

**대상**: 공유 링크 — `GET /share/{token}`, `GET /share/{token}/photos/{photo_id}/image`. (공유 링크 생성은 앨범 API이므로 Album 대시보드에서 다룰 수 있음.)

### 7.1 Row 배치 및 패널

| Row | 제목 | 패널 (좌→우) | 시각화 | 가로축 / 세로축 |
|-----|------|----------------|--------|------------------|
| **1** | **요약** | 공유 링크 접근 성공률(%), 공유 이미지 접근 성공률(%), 공유 링크 P95(초), 브루트포스 시도(분당) | Stat 4개 | — / %, 초, 건·분당 |
| **2** | **요청량** | Nginx: /share 요청(가능 시), API: share_link_access vs share_link_image_access | Time series | 시간 / req/s 또는 건·분당 |
| **3** | **공유 링크 접근** | token_status(valid/invalid/expired), result(success/denied)별 건수 또는 비율 | Time series + Pie | 시간 / 건·분당, % |
| **4** | **공유 이미지 접근** | photo_in_album yes/no, token_status별 건수 또는 비율 | Time series + Pie | 시간 / 건·분당, % |
| **5** | **지연** | 공유 링크 접근 P95, (선택) 공유 이미지 접근 P95(동일 메트릭에 공유 이미지 구간 있으면) | Time series | 시간 / 초(sec) |
| **6** | **보안** | 브루트포스 시도 추이, 상위 IP( client_id ) Table | Time series + Table | 시간 / 건·분당, client_id·건수 |

### 7.2 패널별 넣을 메트릭·쿼리 (구체)

| Row | 패널 제목 | 사용 메트릭 / PromQL | 시각화 | 소스 | 단위(Unit) | 비고 |
|-----|-----------|----------------------|--------|------|------------|------|
| **1** | 공유 링크 접근 성공률(%) | `sum(rate(photo_api_share_link_access_total{result="success"}[5m])) / sum(rate(photo_api_share_link_access_total[5m])) * 100` | Stat | API | `percent (0-100)` | |
| **1** | 공유 이미지 접근 성공률(%) | `sum(rate(photo_api_share_link_image_access_total{photo_in_album="yes"}[5m])) / sum(rate(photo_api_share_link_image_access_total[5m])) * 100` | Stat | API | `percent (0-100)` | yes=정상 접근 |
| **1** | 공유 링크 P95(초) | `histogram_quantile(0.95, sum(rate(photo_api_share_link_access_duration_seconds_bucket[5m])) by (le))` | Stat | API | `s` (초) | |
| **1** | 브루트포스 시도(분당) | `sum(rate(photo_api_share_link_brute_force_attempts_total[5m])) * 60` | Stat | API | `reqm` (건/분) | 무효 토큰 시도 |
| **2** | 공유 링크 접근 vs 이미지 접근 | `sum(rate(photo_api_share_link_access_total[5m])) * 60`, `sum(rate(photo_api_share_link_image_access_total[5m])) * 60` (시리즈 2개) | Time series | API | `reqm` (건/분) | Y축: 건/분 |
| **2** | /share 요청(분당) | `sum(rate(http_requests_total{handler=~"/share.*"}[5m])) * 60` | Time series | API | `reqm` (건/분) | |
| **3** | token_status·result별 건수 | `sum by (token_status, result) (rate(photo_api_share_link_access_total[5m])) * 60` | Time series + Pie | API | `reqm` (건/분) | |
| **4** | photo_in_album yes/no | `sum by (token_status, photo_in_album) (rate(photo_api_share_link_image_access_total[5m])) * 60` | Time series + Pie | API | `reqm` (건/분) | |
| **5** | 공유 링크 P95 추이 | `histogram_quantile(0.95, sum(rate(photo_api_share_link_access_duration_seconds_bucket[5m])) by (le))` | Time series | API | `s` (초) | Y축: 초(sec) |
| **6** | 브루트포스 추이(분당) | `sum(rate(photo_api_share_link_brute_force_attempts_total[5m])) * 60` | Time series | API | `reqm` (건/분) | |
| **6** | 상위 IP( client_id ) | `topk(10, sum by (client_id) (rate(photo_api_share_link_brute_force_attempts_total[5m])) * 60)` | Table | API | `reqm` (건/분), client_id | client_id, 건/분 |

**참고**: 공유 이미지 단일 요청 지연은 현재 `photo_api_share_link_access_duration_seconds`(페이지 접근)와 별도 Histogram이 없음. 공유 이미지 P95가 필요하면 아래 “서버 보완” 참고.

### 7.3 배치 요약

- Row 1: Stat 4개 — 접근 성공률·이미지 성공률·지연·브루트포스.
- Row 2: Nginx + API 요청량.
- Row 3~4: 토큰 상태·결과·photo_in_album 비율(Pie + Time series).
- Row 5: 지연.
- Row 6: 보안(브루트포스 추이 + IP Table).

---

## 8. Nginx 메트릭 수집 요약 (운영 관점)

| 목적 | stub_status만 있을 때 | 로그/Plus 있을 때 |
|------|------------------------|---------------------|
| 전체 트래픽 | `nginx_http_requests_total` rate → RPS | 동일 + 경로별 RPS |
| 에러율 | Nginx 단에서 상태 코드 없을 수 있음 → API 5xx로 대체 | 경로별 4xx/5xx 비율 |
| 지연 | 없음 → API 지연만 사용 | `upstream_response_time` 기반 P95 등 |
| 연결 수 | `nginx_connections_active` 등 | 동일 |

- **SLO Overview**: Nginx는 “전체 RPS + 연결 수”로 부하·가용성 보조.
- **서비스별 대시보드**: 로그/Plus로 경로별 메트릭이 있으면 `/auth`, `/albums`, `/photos`, `/share` 구간별 패널 추가; 없으면 API handler별 메트릭만으로 구성해도 됩니다.

---

## 9. 서버에서 추가·보완하면 좋은 부분

현재 앱에서 이미 수집 중인 메트릭을 전제로, **대시보드에 넣으면 좋은 것**과 **추가 수집을 권장하는 것**을 정리했습니다.

### 9.1 이미 수집 중인데 대시보드에 넣으면 좋은 메트릭

| 메트릭 | 수집 위치 | 넣을 대시보드·패널 | 비고 |
|--------|-----------|---------------------|------|
| `photo_api_health_check_status` | health 라우터 (check_type: fast / detailed) | SLO Overview Row 2 “스택 상태” | 1=통과, 0=실패. 헬스체크 실패 시 원인 범위 좁히기 |
| `photo_api_db_pool_active_connections` | database.py (연결 풀) | SLO Overview Row 2 또는 별도 “DB 풀” 행 | 풀 사용량. 고갈 전 알림 |
| `photo_api_db_pool_waiting_requests` | database.py (overflow) | 동일 | 대기 요청 증가 시 스케일·풀 크기 검토 |
| `photo_api_circuit_breaker_state` | circuit_breaker.py (service별) | SLO Overview 또는 “외부 의존성” 행 | 0=closed, 1=open, 2=half-open. obs_api_server/cdn_api_server 등 |
| `photo_api_in_flight_requests` | RequestTrackingMiddleware | SLO Overview “처리 중 요청 수” | Graceful shutdown·부하 판단 보조 |

위 메트릭은 **이미 코드에 있으므로** Prometheus 스크래핑만 하면 되고, 대시보드에 패널만 추가하면 됩니다.

### 9.2 수집·노출을 추가하면 좋은 부분

| 항목 | 현재 상태 | 제안 | 목적 |
|------|-----------|------|------|
| **공유 이미지 접근 지연** | `photo_api_share_link_access_duration_seconds`는 “공유 링크 페이지” 접근만 측정. 이미지 GET(`/share/{token}/photos/{id}/image`) 지연은 별도 Histogram 없음 | 공유 이미지 엔드포인트에서 `photo_api_image_access_duration_seconds.labels(access_type="shared", result=...)` 기록 또는 `photo_api_share_link_image_access_duration_seconds` Histogram 신규 추가 | Share 대시보드에서 “공유 이미지 P95” 패널 구성, 장애 시나리오 §9.10에서 지연 원인 구분 |
| **이미지 접근(access_type=shared)** | `photo_api_image_access_total` 은 인증(authenticated)만 기록. 공유 이미지는 `share_link_image_access_total` 만 있음 | `/share/{token}/photos/{id}/image` 처리 시 `image_access_total.labels(access_type="shared", result=...)` 추가 | SLO Overview “이미지 접근 성공률”을 인증+공유 통합 또는 Share 전용으로 일관되게 표시 |
| **회원가입 전용 메트릭** | 회원가입 성공/실패는 `http_requests_total{handler=~".*register"}` 로만 구분 가능 | (선택) `photo_api_register_total` Counter (result: success/failure) 추가 | User 대시보드에서 “회원가입 성공률” Stat을 Instrumentator 의존 없이 안정적으로 표시 |
| **Nginx 메트릭** | 문서에서 가정만 함. 실제로 stub_status 또는 로그 기반 수집이 없을 수 있음 | Nginx 앞단 사용 시: nginx-prometheus-exporter(stub_status) 또는 access log 파싱(경로별·상태별·upstream_response_time) 도입 | SLO Overview·서비스별에서 Nginx RPS·연결 수·(가능 시) 경로별 에러율·지연 표시 |
| **외부 서비스 라벨** | `obs_api_server`, `cdn_api_server`, `log_api_server` (API 서버→OBS/CDN/Log 구간) | 대시보드·알림 쿼리에서 동일 라벨 사용. | 쿼리 오류 방지, 의미 명확화 |
| **HTTP handler 라벨** | Instrumentator가 노출하는 `handler` 값(경로)이 앱 라우팅에 따라 다름(예: `/auth/login` vs `/api/auth/login`) | Grafana 변수 또는 쿼리에서 실제 노출된 `handler` 값 확인 후 `handler=~".*login"` 등으로 매칭 | prefix가 `/api` 인 경우 `handler=~"/api/auth.*"` 등으로 조정 |

### 9.3 알림·검증 보완

| 항목 | 제안 |
|------|------|
| **헬스체크 실패 알림** | `photo_api_health_check_status == 0` (check_type별) 일정 시간 지속 시 알림. 상세(detailed) 실패 시 DB·스토리지 등 의존성 점검 |
| **DB 풀 고갈 전 알림** | `photo_api_db_pool_waiting_requests` > 0 지속 또는 `photo_api_db_pool_active_connections` 가 풀 max에 근접 시 Warning |
| **Circuit breaker open 알림** | `photo_api_circuit_breaker_state{service=~"obs_api_server|cdn_api_server|log_api_server"} == 1` 일정 시간 지속 시 해당 API 서버 의존성 장애로 알림 |

이 반영 시 대시보드에 “넣을 메트릭”이 더 구체적으로 정해지고, 장애 시나리오별로 필요한 지표를 서버에서 빠짐없이 쓸 수 있습니다.

---

## 10. 장애 시나리오별 필요 메트릭 및 이유

아래는 **장애 시나리오**별로 **어떤 메트릭이 왜 필요한지**를 정리한 표입니다. 알림 설정·대응 플로우 설계 시 참고하세요.

---

### 10.1 서비스/인스턴스 다운

| 시나리오 | 현상 | 필요한 메트릭 | 왜 필요한지 | 참고 대시보드 |
|----------|------|----------------|-------------|----------------|
| API 프로세스 죽음·재시작 | 헬스체크 실패, 요청 무응답 | `photo_api_ready` | 0이면 해당 인스턴스가 트래픽 수신 불가. LB에서 제거·재기동 판단에 사용. | SLO Overview |
| 일부 인스턴스만 다운 | 나머지 인스턴스 과부하, 5xx 증가 가능 | `count(photo_api_ready == 1)`, `photo_api_app_info` | 정상 인스턴스 수·어느 노드가 빠졌는지 확인. 스케일·롤링 배포 중 이상 여부 판단. | SLO Overview |
| Nginx가 API에 연결 못 함 | 502 Bad Gateway | Nginx upstream 상태·연결 수, `photo_api_ready` | Nginx 쪽에서 “업스트림 죽음” vs “일시적 타임아웃” 구분. API ready로 원인이 API 다운인지 확인. | SLO Overview |

---

### 10.2 5xx 에러율 급증 (전체 또는 특정 경로)

| 시나리오 | 현상 | 필요한 메트릭 | 왜 필요한지 | 참고 대시보드 |
|----------|------|----------------|-------------|----------------|
| 전체 API 5xx 증가 | 사용자 전반 에러 경험 | `http_requests_total{status=~"5.."}`, `http_requests_total` (전체) | 5xx/전체 비율로 장애 규모·SLA 위반 여부 판단. 알림 임계값(예: 1%, 5%) 설정 기준. | SLO Overview |
| 특정 경로만 5xx | 로그인·업로드·앨범 등 일부만 실패 | `http_requests_total` by `handler`, `status` | handler별 5xx로 “어느 API가 깨졌는지” 좁히기. User/Album/Image/Share 대시보드에서 해당 도메인만 집중. | User, Album, Image, Share |
| Nginx 단 5xx (502/504) | 업스트림 타임아웃·연결 실패 | Nginx 경로별·상태 코드별 요청 수(로그 기반 등) | API는 200인데 Nginx가 502를 준다면 Nginx↔API 구간·타임아웃 이슈. Nginx 메트릭으로 원인 범위 분리. | SLO Overview |

---

### 10.3 응답 지연·병목 (전체 또는 특정 핸들러)

| 시나리오 | 현상 | 필요한 메트릭 | 왜 필요한지 | 참고 대시보드 |
|----------|------|----------------|-------------|----------------|
| 전체 API 느려짐 | P95/P99 급상승, 타임아웃 증가 | `http_request_duration_seconds` (P50/P95/P99) | “전체가 느린지” 확인. DB·외부 서비스·CPU 등 원인 후보와 시간대 맞춰 비교. | SLO Overview |
| 특정 API만 느림 | 로그인·이미지·공유 등 일부만 지연 | `photo_api_login_duration_seconds`, `photo_api_image_access_duration_seconds`, `photo_api_share_link_access_duration_seconds`, handler별 `http_request_duration_seconds` | “어느 플로우가 병목인지” 특정. 로그인→DB/해싱, 이미지→CDN/스토리지, 공유→토큰 검증/DB 점검. | User, Image, Share |
| Nginx↔API 구간 지연 | Nginx 로그에 upstream_response_time 큼 | Nginx upstream 응답 시간(로그/Plus) | API 자체 지연은 작은데 사용자 체감이 크면 Nginx↔API·네트워크 구간 의심. Nginx 지연 메트릭으로 검증. | SLO Overview |

---

### 10.4 DB 장애

| 시나리오 | 현상 | 필요한 메트릭 | 왜 필요한지 | 참고 대시보드 |
|----------|------|----------------|-------------|----------------|
| DB 연결 실패·풀 고갈 | 로그인·앨범·이미지 목록 등 DB 쓰는 API 전반 5xx/지연 | `photo_api_db_errors_total` | DB 에러가 급증한 시점과 5xx·지연 시점이 일치하면 원인을 DB로 좁힘. | SLO Overview, User, Album |
| DB 쿼리 지연 | 응답 시간만 올라가고 5xx는 적음 | `http_request_duration_seconds` by handler, `photo_api_login_duration_seconds`, `photo_api_share_link_access_duration_seconds` | 로그인·공유(토큰/앨범 조회) 등 DB 의존 경로의 P95가 먼저 올라가면 DB 병목 의심. | User, Share, SLO Overview |

---

### 10.5 외부 서비스 장애 (Object Storage, CDN, Log)

| 시나리오 | 현상 | 필요한 메트릭 | 왜 필요한지 | 참고 대시보드 |
|----------|------|----------------|-------------|----------------|
| Object Storage 장애 | 업로드 실패, 이미지 스트리밍 실패 | `photo_api_external_request_errors_total{service="obs_api_server"}`, `photo_api_photo_upload_confirm_total`, `photo_api_image_access_total` | 외부 에러 카운트로 “스토리지 문제” 판단. 업로드 확인·이미지 접근 실패와 시간대 맞추면 원인 확정에 가까움. | Image, SLO Overview |
| CDN 장애 | 토큰 발급 실패, 이미지 리다이렉트 실패 | `photo_api_external_request_errors_total{service="cdn"}`, `photo_api_image_access_duration_seconds` | CDN 에러 증가 시 이미지 로딩이 백엔드 스트리밍으로 넘어가거나 실패. 지연·실패율 동시 확인. | Image, SLO Overview |
| Log Service 장애 | 로그 적재 지연·실패 | `photo_api_log_queue_size`, `photo_api_external_request_errors_total{service="log_service"}` | 로그 큐가 계속 쌓이면 Log 전송 실패. 큐 크기로 백프레셔·메모리 위험 감지. | SLO Overview (안정성 행) |

---

### 10.6 Nginx 장애·업스트림 타임아웃

| 시나리오 | 현상 | 필요한 메트릭 | 왜 필요한지 | 참고 대시보드 |
|----------|------|----------------|-------------|----------------|
| 업스트림 타임아웃(502/504) | Nginx는 살아 있는데 API 응답 지연·무응답 | Nginx upstream 응답 시간·상태, `photo_api_ready`, `http_request_duration_seconds` | Nginx가 502/504를 주는 시점에 API P95·ready 상태 확인. API가 느리면 API 쪽 조치, API는 정상이면 Nginx 타임아웃·네트워크 검토. | SLO Overview |
| Nginx 연결 폭주 | too many open connections 등 | `nginx_connections_active`, `nginx_connections_reading` 등 | 연결 수 급증 시 Nginx나 upstream에서 연결을 못 받는 상태. 스케일·limit 설정 점검. | SLO Overview |

---

### 10.7 로그인 실패 급증 (인증 장애 vs 브루트포스)

| 시나리오 | 현상 | 필요한 메트릭 | 왜 필요한지 | 참고 대시보드 |
|----------|------|----------------|-------------|----------------|
| 인증 서버/DB 문제로 로그인 실패 | 정상 사용자도 로그인 불가 | `http_requests_total{handler=~".*login"}`, status별, `photo_api_login_duration_seconds`, `photo_api_db_errors_total` | 로그인 5xx·실패율 상승 + DB 에러 또는 로그인 지연 상승이면 “시스템 장애”. DB·해싱·네트워크 점검. | User |
| 브루트포스·자격 증명 시도 | 무차별 로그인 시도, 401 다수 | `http_requests_total{handler=~".*login",status="401"}`, 로그인 시도 건수 대비 성공률 | 401 급증 + 성공률 급락이면 공격 가능성. Rate limit·IP 차단 검토. (로그인은 보통 rate limit 별도 적용) | User |
| 로그인 지연만 증가 | 성공은 하는데 느림 | `photo_api_login_duration_seconds` (P95) | DB 쿼리·해싱 병목 여부 판단. 인덱스·리소스 점검. | User |

---

### 10.8 업로드 실패 (Presigned, 확인, 스토리지)

| 시나리오 | 현상 | 필요한 메트릭 | 왜 필요한지 | 참고 대시보드 |
|----------|------|----------------|-------------|----------------|
| Presigned URL 발급 실패 | 클라이언트가 업로드 시작도 못 함 | `photo_api_presigned_url_generation_total` (result별) | failure 급증 시 “업로드 진입” 단계에서 막힘. IAM·스토리지 설정·앱 로직 점검. | Image |
| 업로드 완료 확인 실패 | 클라이언트는 업로드했는데 서버에 반영 안 됨 | `photo_api_photo_upload_confirm_total` (result별), `photo_api_external_request_errors_total{service="obs_api_server"}` | confirm failure = 실제 저장·메타 반영 실패. 스토리지 에러와 함께 보면 원인(스토리지/네트워크/타임아웃) 구분. | Image |
| 업로드 전체 실패율 상승 | presigned/direct 모두 실패 증가 | `photo_api_photo_upload_total` (upload_method, result) | presigned vs direct 둘 다 나쁘면 공통 원인(스토리지·네트워크·앱). 한쪽만 나쁘면 해당 경로만 점검. | Image |

---

### 10.9 이미지 로딩 실패·지연

| 시나리오 | 현상 | 필요한 메트릭 | 왜 필요한지 | 참고 대시보드 |
|----------|------|----------------|-------------|----------------|
| 이미지 접근 실패(권한·없음) | 403/404, denied 증가 | `photo_api_image_access_total` (result=denied vs success) | denied 비율로 “권한 거부·리소스 없음” 규모 파악. 정책·클라이언트 버그 구분. | Image |
| 이미지 로딩 지연 | 스피너 길어짐, P95 상승 | `photo_api_image_access_duration_seconds`, `photo_api_external_request_duration_seconds{service="obs_api_server"}` | 이미지 지연이 스토리지 지연과 같이 올라가면 스토리지/네트워크. CDN 사용 시 리다이렉트만 느리면 CDN·토큰 발급 확인. | Image |
| CDN 장애로 백엔드 쏠림 | 이미지 전부 백엔드 경유, 지연·부하 증가 | `photo_api_image_access_duration_seconds`, `photo_api_external_request_errors_total{service="cdn"}`, 이미지 접근 건수 | CDN 에러 증가 + 이미지 접근 지연·건수 동시 확인. CDN 복구 또는 임시로 백엔드만 사용 시 리소스 모니터링. | Image, SLO Overview |

---

### 10.10 공유 링크·공유 이미지 접근 실패

| 시나리오 | 현상 | 필요한 메트릭 | 왜 필요한지 | 참고 대시보드 |
|----------|------|----------------|-------------|----------------|
| 토큰 만료·무효로 접근 실패 | 사용자가 “만료됐다” 경험 | `photo_api_share_link_access_total` (token_status=expired/invalid, result=denied) | 만료/무효 비율로 “정상적인 만료” vs “설정/클라이언트 이슈” 구분. 만료 시간 정책 검토. | Share |
| 브루트포스(무효 토큰 대량 시도) | 공유 링크 추측 공격 | `photo_api_share_link_brute_force_attempts_total`, client_id별, `photo_api_share_link_access_total{token_status="invalid"}` | 무효 시도·IP별 시도로 공격 탐지. Rate limit·IP 차단·알림 트리거. | Share |
| 다른 앨범 사진 접근 시도(권한 오남용) | 토큰은 유효한데 해당 앨범에 없는 사진 요청 | `photo_api_share_link_image_access_total{photo_in_album="no"}` | no 비율이 높으면 URL 추측·오남용 가능성. 보안 정책·알림 검토. | Share |
| 공유 링크/이미지 응답 지연 | 공유 페이지·이미지 로딩 느림 | `photo_api_share_link_access_duration_seconds`, `photo_api_image_access_duration_seconds{access_type="shared"}` (공유 이미지 메트릭 있을 때) | 토큰 검증·DB·앨범 조회 병목 여부. 공유 이미지는 스토리지/CDN 지연과 함께 확인. | Share |

---

### 10.11 Rate limit 과다 차단 (DDoS vs 설정 오류)

| 시나리오 | 현상 | 필요한 메트릭 | 왜 필요한지 | 참고 대시보드 |
|----------|------|----------------|-------------|----------------|
| DDoS·비정상 트래픽 | 특정 IP·엔드포인트에서 차단 급증 | `photo_api_rate_limit_hits_total` (endpoint, client_id), `photo_api_rate_limit_requests_total` (allowed/blocked) | 차단 건수·비율로 공격 규모 파악. client_id·endpoint별로 우선 차단/대응 대상 식별. | SLO Overview (보안), Share |
| 정상 사용자까지 과도하게 차단 | 차단률이 높은데 트래픽은 평소와 비슷 | `photo_api_rate_limit_requests_total` (allowed vs blocked 비율), 요청량 추이 | 차단률이 높으면 limit 값이 너무 낮거나 버스트 미고려. 설정 상향·알림 임계값 조정. | SLO Overview |

---

### 10.12 리소스 고갈 (CPU, 메모리, 디스크, 로그 큐)

| 시나리오 | 현상 | 필요한 메트릭 | 왜 필요한지 | 참고 대시보드 |
|----------|------|----------------|-------------|----------------|
| CPU 포화 | 응답 지연·타임아웃 증가 | `node_cpu_seconds_total` (rate → 사용률), `http_request_duration_seconds` | CPU 사용률과 P95가 같이 올라가면 CPU 병목. 스케일 아웃·코드 최적화 검토. | SLO Overview, 리소스 대시보드 |
| 메모리 부족·OOM 위험 | 프로세스 kill, 5xx | `node_memory_*` (사용률), `photo_api_log_queue_size` | 메모리 사용률 상승 + 로그 큐 폭주 시 로그 버퍼가 원인일 수 있음. 큐 크기·로그 전송 상태 점검. | SLO Overview |
| 디스크 가득 참 | 로그·임시 파일 쓰기 실패, 앱 이상 | `node_filesystem_avail_bytes` (또는 사용률) | 디스크 부족 전에 로그 로테이션·정리·볼륨 확장. | SLO Overview, 리소스 대시보드 |
| 로그 큐 백프레셔 | 로그 전송이 밀려 메모리 증가 | `photo_api_log_queue_size` | 큐가 계속 증가하면 Log Service 장애 또는 네트워크 이슈. 전송 재시도·폐기 정책 점검. | SLO Overview |

---

### 10.13 앨범 작업 실패

| 시나리오 | 현상 | 필요한 메트릭 | 왜 필요한지 | 참고 대시보드 |
|----------|------|----------------|-------------|----------------|
| 앨범 CRUD 실패 | 생성·수정·삭제 5xx | `album_operations_total` (operation, result), `http_requests_total{handler=~"/albums.*"}`, `photo_api_db_errors_total` | operation별 failure로 “어느 작업이 깨졌는지” 파악. DB 에러와 함께 보면 DB 원인 여부 확인. | Album |
| 앨범-사진 추가/삭제 실패 | 사진 넣기·빼기 실패 | `album_photo_operations_total` (operation, result) | add/remove failure = 권한·제약·DB 이슈. 앨범·사진 메타 정합성 점검. | Album |

---

### 10.14 요약: 장애 유형 → 우선 확인할 대시보드·메트릭

| 장애 유형 | 우선 확인 대시보드 | 핵심 메트릭 (원인 좁히기용) |
|-----------|---------------------|-----------------------------|
| 서비스 다운 | SLO Overview | `photo_api_ready`, `count(photo_api_ready==1)` |
| 5xx 급증 | SLO Overview → handler별로 User/Album/Image/Share | `http_requests_total` by handler, status |
| 지연·병목 | SLO Overview → 도메인별 대시보드 | `http_request_duration_seconds`, `photo_api_*_duration_seconds` |
| DB 장애 | SLO Overview, User, Album, Share | `photo_api_db_errors_total`, 해당 handler 지연·5xx |
| 외부 서비스 장애 | Image, SLO Overview | `photo_api_external_request_errors_total`, `photo_api_log_queue_size` |
| Nginx 502/504 | SLO Overview | Nginx upstream·연결, `photo_api_ready`, API P95 |
| 로그인 문제 | User | 로그인 handler 2xx/5xx, `photo_api_login_duration_seconds`, DB 에러 |
| 업로드 문제 | Image | presigned/confirm/upload total, `external_request_errors` object_storage |
| 이미지 로딩 문제 | Image | `image_access_total`, `image_access_duration_seconds`, CDN/스토리지 에러 |
| 공유 링크 문제 | Share | `share_link_access_total`, `share_link_image_access_total`, brute_force |
| Rate limit 이슈 | SLO Overview, Share | `rate_limit_hits_total`, `rate_limit_requests_total` |
| 리소스 고갈 | SLO Overview, 리소스 | `node_cpu_*`, `node_memory_*`, `node_filesystem_*`, `photo_api_log_queue_size` |
| 앨범 작업 실패 | Album | `album_operations_total`, `album_photo_operations_total`, DB 에러 |

---

## 11. 관련 문서

- **지표 정의·수집 이유**: `docs/monitoring/SERVICE-MONITORING-DASHBOARD.md`
- **SLA 대시보드 만드는 방법·쿼리**: `docs/monitoring/SERVICE-MONITORING-DASHBOARD.md` §9, 루트 `MONITORING_VISUALIZATION.md`
- **알림·지표 상세**: `HA_MONITORING_METRICS.md`
