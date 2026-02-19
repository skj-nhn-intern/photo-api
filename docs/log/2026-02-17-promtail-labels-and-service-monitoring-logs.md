# Promtail 라벨 추가 및 서비스 모니터링 로그 구체화

**작성일**: 2026-02-17

이 문서는 서비스 모니터링을 위해 Promtail에 추가한 라벨, 수집할 로그의 구체적 정의, 그리고 보완 메트릭 제안을 정리한 것입니다.

---

## 1. Promtail 라벨 추가 내역

설정 파일: `conf/promtail-config.yaml`. 적용 대상 job: `photo-api`, `photo-api-errors`.

### 1.1 추가된 라벨

| 라벨 | 추출 위치 | 용도 | 비고 |
|------|------------|------|------|
| `event` | JSON `event` | 이벤트별 건수 추이 (user_login, auth, db, cdn, request 등) | 기존 추가 분 반영 |
| `level` | JSON `level` | 로그 레벨별 건수·ERROR/WARNING 비율 | INFO, WARNING, ERROR |
| `path_prefix` | JSON `http_path` (정규식) | 서비스 구간별 필터: `/auth`, `/albums`, `/photos`, `/share` | 정규식 `^(?P<path_prefix>/auth\|/albums\|/photos\|/share)` |

### 1.2 파이프라인 순서 (요약)

1. `json`: timestamp, instance_ip, host, **event**, **level**, **http_path** 추출  
2. `labels`: instance_ip, **event**, **level**  
3. `regex`: `http_path` 값에서 **path_prefix** 추출 (매칭 시에만)  
4. `labels`: **path_prefix**  
5. `timestamp`: timestamp 파싱  

### 1.3 적용 방법

- Promtail 설정 리로드 또는 재시작.
- **이후 수집되는 로그**부터 새 라벨이 붙습니다. 기존 로그는 라벨이 없습니다.

### 1.4 호환성

- `regex` 단계의 `source: http_path`는 Promtail 2.x에서 지원. 구버전이면 해당 단계와 `path_prefix` 라벨 추가 구간을 제거하고, 쿼리에서 `| json | http_path=~"/auth.*"` 등으로 필터하면 됩니다.

---

## 2. 서비스 모니터링을 위한 로그 구체화

### 2.1 수집 대상 로그

| 소스 | 경로 | 내용 |
|------|------|------|
| 앱 전체 | `/var/log/photo-api/app.log` | 구조화 JSON 한 줄 단위 (모든 레벨) |
| 에러 전용 | `/var/log/photo-api/error.log` | ERROR 이상만 (동일 JSON 구조) |

- 서비스 모니터링에는 **app.log** 수집만으로도 가능. error.log는 에러 집중 조회·알림용으로 선택 사용.

### 2.2 필수 로그 필드 (앱 출력·Loki 쿼리 기준)

앱 `JsonLinesFormatter`가 출력하는 JSON 한 줄 기준. **서비스별 모니터링**에 필요한 필드는 아래와 같다.

| 필드 | 타입 | 필수 여부 | 용도 |
|------|------|-----------|------|
| `timestamp` | string (ISO 8601) | 필수 | 시간 구간·시계열 |
| `level` | string | 필수 | ERROR/WARNING 비율, 로그 레벨별 건수 |
| `service` | string | 필수 | 앱 식별 |
| `message` | string | 필수 | 원인 파악 |
| `event` | string | 권장 | 이벤트별 분포 (auth, user_login, db, cdn, request 등) |
| `http_method` | string | 요청 시 | 메서드별 집계 |
| `http_path` | string | 요청 시 | **서비스 구간 필터** (User/Album/Image/Share) |
| `http_status` | number | 요청 시 | 4xx/5xx 비율, 성공률 |
| `duration_ms` | number | 요청 시 | 지연 추이·P95 등 |
| `client_ip` | string | 요청 시 | IP별 401·rate limit 집계 (보안) |
| `request_id` | string | 요청 시 | 요청 추적 |
| `error_type`, `error_message`, `error_code` | string | 에러 시 | 원인 분류 |
| `context` | object | 선택 | reason, user_id 등 추가 맥락 |

### 2.3 서비스별로 보는 로그 (path_prefix / http_path)

| 서비스 | 경로 조건 | 사용 라벨/필드 | 대시보드 |
|--------|-----------|----------------|----------|
| **User (Auth)** | `http_path=~"/auth.*"` 또는 라벨 `path_prefix="/auth"` | event=user_login, user_registration, auth / http_status, client_ip | User (Auth) |
| **Album** | `http_path=~"/albums.*"` 또는 `path_prefix="/albums"` | event, http_status, duration_ms | Album |
| **Image** | `http_path=~"/photos.*"` 또는 `path_prefix="/photos"` | event=photo_upload, photo_presigned, photo_stream 등 + level / http_status, duration_ms | Image |
| **Share** | `http_path=~"/share.*"` 또는 `path_prefix="/share"` | event=share_link_create, share_access, share_stream + level / http_status, client_ip | Share |

- **라벨 사용**: `{job="photo-api", path_prefix="/auth"}` 로 User 서비스만 선택 가능.  
- **본문 필터**: 라벨 없이 쿼리 시 `{job="photo-api"} | json | http_path=~"/auth.*"`.

### 2.4 서비스 모니터링용 LogQL 예시 (라벨 활용)

- **event별 건수 (전체)**  
  `sum by (event) (count_over_time({job="photo-api"}[5m]))`
- **로그 레벨별 건수**  
  `sum by (level) (count_over_time({job="photo-api"}[5m]))`
- **ERROR 비율 (건수 기준)**  
  `sum(count_over_time({job="photo-api", level="ERROR"}[5m])) / sum(count_over_time({job="photo-api"}[5m])) * 100`
- **서비스(User) 로그만 event별**  
  `sum by (event) (count_over_time({job="photo-api", path_prefix="/auth"}[5m]))`
- **서비스(Album) 4xx/5xx 건수**  
  `{job="photo-api", path_prefix="/albums"} | json | http_status>=400` 후 건수 집계 또는 메트릭 쿼리로 유도.

---

## 3. 추가 모니터링 메트릭 제안

### 3.1 로그 기반 (Loki)으로 추가 권장

| 지표 | 쿼리 개요 | 용도 |
|------|------------|------|
| **로그 레벨별 건수** | `sum by (level) (count_over_time({job="photo-api"}[5m]))` | ERROR/WARNING 추이, SLO Overview 등 |
| **서비스(path_prefix)별 로그 건수** | `sum by (path_prefix) (count_over_time({job="photo-api"}[5m]))` | 서비스별 로그량·트렌드 |
| **User 서비스 401 건수 (client_ip별)** | `{job="photo-api", path_prefix="/auth"} \| json \| http_status=401` → client_ip 그룹 집계 | 로그인 실패·브루트포스 후보 IP |

### 3.2 앱 메트릭(Prometheus) 추가 권장 (선택)

| 메트릭 | 목적 | 비고 |
|--------|------|------|
| **로그인 실패 건수 (client_id별)** | `photo_api_login_failures_total{client_id="..."}` | Loki 없이도 401·IP별 집계 가능. 개인정보 고려해 client_id는 IP 일부만. |
| **로그 레벨별 Counter** | `photo_api_log_events_total{level="ERROR"}` 등 | 로그 수집 전에도 ERROR 건수 알림 가능. |

- 현재는 **로그(Loki) + Promtail 라벨**만으로 서비스 모니터링·event/level/서비스별 현황을 충분히 구성할 수 있음. 위 Prometheus 메트릭은 알림 정밀도·Loki 부담을 줄이고 싶을 때 검토하면 됨.

---

## 4. 관련 문서

- **대시보드 배치·쿼리**: `docs/monitoring/DASHBOARD-LAYOUT-SLO-SERVICE.md`  
- **전송 로그 구조·event 횟수 현황**: 동 문서 § "Photo API 전송 로그 구조", "event 횟수 현황"  
- **Promtail 설정**: `conf/promtail-config.yaml`
