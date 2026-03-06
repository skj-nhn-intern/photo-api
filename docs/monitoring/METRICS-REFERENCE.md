# Photo API Prometheus 메트릭 세부 사항

이 문서는 Photo API가 `/metrics`로 노출하는 **모든 Prometheus 메트릭**의 이름, 타입, 라벨, 갱신 방식, 용도를 정리합니다.  
정의 위치: `app/utils/prometheus_metrics.py` (일부는 `app/database.py`, `app/routers/health.py`).

---

## 목차

1. [안정성 (Stability)](#1-안정성-stability)
2. [고가용성 (HA)](#2-고가용성-ha)
3. [성능 (Performance)](#3-성능-performance)
4. [Rate Limiting](#4-rate-limiting)
5. [공유 링크 (Share Link)](#5-공유-링크-share-link)
6. [이미지 접근 (Image Access)](#6-이미지-접근-image-access)
7. [사진 업로드 (Photo Upload)](#7-사진-업로드-photo-upload)
8. [앨범 (Album)](#8-앨범-album)
9. [비즈니스·성장 지표 (Business)](#9-비즈니스성장-지표-business)
10. [Object Storage 사용량](#10-object-storage-사용량)
11. [인증 (Auth)](#11-인증-auth)
12. [커스텀 컬렉터 (Top 10·종류별)](#12-커스텀-컬렉터)
13. [DB 연결 풀](#13-db-연결-풀)
14. [헬스체크](#14-헬스체크)
15. [앱 식별 (setup 시 등록)](#15-앱-식별)

---

## 1. 안정성 (Stability)

| 메트릭 이름 | 타입 | 라벨 | 설명 | 갱신 시점 |
|-------------|------|------|------|------------|
| `photo_api_exceptions_total` | Counter | — | 처리되지 않은 예외 발생 횟수 | 전역 예외 핸들러에서 `.inc()` |
| `photo_api_db_errors_total` | Counter | — | DB 세션/트랜잭션 에러 횟수 | `get_db()` 예외 시 `.inc()` |
| `photo_api_external_request_errors_total` | Counter | `service` | 외부 API 호출 실패 횟수. service: `obs_api_server`, `cdn_api_server`, `log_api_server` | `record_external_request(service)` 예외 시 |
| `photo_api_external_request_total` | Counter | `service`, `status` | 외부 API 요청 수. status: `success` \| `failure` | `record_external_request()` 성공/실패 시 |

---

## 2. 고가용성 (HA)

| 메트릭 이름 | 타입 | 라벨 | 설명 | 갱신 시점 |
|-------------|------|------|------|------------|
| `photo_api_ready` | Gauge | `region` | 앱 준비 상태. 1=트래픽 수신 가능, 0=종료 중. region=REGION env | lifespan: startup 성공 시 1, 검증 실패/종료 시 0 |

---

## 3. 성능 (Performance)

| 메트릭 이름 | 타입 | 라벨 | 설명 | 갱신 시점 |
|-------------|------|------|------|------------|
| `photo_api_external_request_duration_seconds` | Histogram | `service`, `result` | 외부 API 요청 소요 시간(초). result: `success` \| `failure` | `record_external_request()` 종료 시 `.observe(duration)` |
| `photo_api_login_duration_seconds` | Histogram | `result` | 로그인 요청 소요 시간(초). result: `success` \| `failure` | 로그인 엔드포인트 처리 시 |
| `photo_api_active_sessions` | Gauge | — | 유효한 인증으로 처리 중인 요청 수 | ActiveSessionsMiddleware에서 요청 시작/종료 시 증감 |
| `photo_api_in_flight_requests` | Gauge | — | 현재 처리 중인 요청 수 (Graceful shutdown용) | RequestTrackingMiddleware에서 요청 시작/종료 시 증감 |

**Histogram 버킷**

- `external_request_duration_seconds`: 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0 (초)
- `login_duration_seconds`: 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 3.0, 5.0 (초)

---

## 4. Rate Limiting

| 메트릭 이름 | 타입 | 라벨 | 설명 | 갱신 시점 |
|-------------|------|------|------|------------|
| `photo_api_rate_limit_hits_total` | Counter | `endpoint`, `client_id` | rate limit에 걸려 차단된 요청 수. client_id는 IP 일부(개인정보 보호) | 차단 시 `.inc()` |
| `photo_api_rate_limit_requests_total` | Counter | `endpoint`, `status` | rate limit 검사 대상 요청 수. status: `allowed` \| `blocked` | 검사 시 `.inc()` |

---

## 5. 공유 링크 (Share Link)

| 메트릭 이름 | 타입 | 라벨 | 설명 | 갱신 시점 |
|-------------|------|------|------|------------|
| `photo_api_share_link_access_total` | Counter | `token_status`, `result`, `access_type` | 공유 링크(앨범 페이지) 접근 시도 수. token_status: valid \| invalid \| expired, result: success \| denied, access_type: shared | share 라우터 GET /share/{token} |
| `photo_api_share_link_brute_force_attempts_total` | Counter | `client_id` | 무효 토큰으로 시도한 횟수 (브루트포스 탐지용) | 무효 토큰 접근 시 |
| `photo_api_share_link_access_duration_seconds` | Histogram | `token_status`, `result`, `access_type` | 공유 링크(앨범) 접근 요청 소요 시간(초) | share 라우터에서 observe |
| `photo_api_share_link_image_access_total` | Counter | `token_status`, `photo_in_album`, `access_type` | 공유 링크로 이미지 접근 시도 수. photo_in_album: yes \| no | GET /share/{token}/photos/{id}/image |
| `photo_api_share_link_creation_total` | Counter | `result` | 공유 링크 생성 시도 수. result: success \| failure | 앨범 라우터에서 링크 생성 시 |
| `photo_api_share_link_access_by_album_total` | Counter | `album_id`, `access_type` | 앨범별 공유 링크 성공 접근 수 (Top 10 시각화용) | 공유 앨범 접근 성공 시 `.labels(album_id=..., access_type="shared").inc()` |

---

## 6. 이미지 접근 (Image Access)

| 메트릭 이름 | 타입 | 라벨 | 설명 | 갱신 시점 |
|-------------|------|------|------|------------|
| `photo_api_image_access_total` | Counter | `access_type`, `result` | 이미지 접근 시도 수. access_type: `authenticated` \| `shared`, result: `success` \| `denied` | 인증/공유 이미지 다운로드 처리 시 |
| `photo_api_image_access_duration_seconds` | Histogram | `access_type`, `result` | 이미지 접근 요청 소요 시간(초) | 이미지 응답 전달 시 observe |

**버킷**: 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0 (초)

---

## 7. 사진 업로드 (Photo Upload)

| 메트릭 이름 | 타입 | 라벨 | 설명 | 갱신 시점 |
|-------------|------|------|------|------------|
| `photo_api_photo_upload_total` | Counter | `upload_method`, `result` | 업로드 시도 수. upload_method: `presigned` \| `direct`, result: success \| failure | 업로드 완료/실패 시 |
| `photo_api_photo_upload_file_size_bytes` | Histogram | `upload_method` | 업로드된 파일 크기(bytes). 버킷: 1KB ~ 10MB | 업로드 처리 시 observe |
| `photo_api_presigned_url_generation_total` | Counter | `result` | OBS Presigned(임시) URL 생성 시도 수. result: success \| failure | Presigned URL 발급 시 |
| `photo_api_cdn_auth_token_requests_total` | Counter | `result`, `access_type` | CDN Auth Token API 요청 수. access_type: authenticated \| shared | 이미지 URL 생성 시 (nhn_cdn) |
| `photo_api_photo_upload_confirm_total` | Counter | `result` | 업로드 확인(confirm) 시도 수. result: success \| failure | confirm 엔드포인트 처리 시 |

---

## 8. 앨범 (Album)

| 메트릭 이름 | 타입 | 라벨 | 설명 | 갱신 시점 |
|-------------|------|------|------|------------|
| `photo_api_album_operations_total` | Counter | `operation`, `result`, `access_type` | 앨범 작업 수. operation: create \| update \| delete, result: success \| failure, access_type: authenticated | 앨범 생성/수정/삭제 시 |
| `photo_api_album_access_duration_seconds` | Histogram | `size_bucket`, `access_type` | 앨범(사진 목록 포함) 조회 소요 시간(초). size_bucket: 앨범 내 사진 수 구간 | 앨범 조회(인증/공유) 완료 시 observe |
| `photo_api_album_photo_operations_total` | Counter | `operation`, `result`, `access_type` | 앨범-사진 작업 수. operation: add \| remove, result: success \| failure, access_type: authenticated | 사진 추가/제거 시 |

**size_bucket** (앨범 내 사진 수 기준):

| 값 | 의미 |
|----|------|
| `empty` | 0장 |
| `small` | 1~10장 |
| `medium` | 11~50장 |
| `large` | 51장 이상 |

**Histogram 버킷** (album_access_duration_seconds): 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0 (초)

---

## 9. 비즈니스·성장 지표 (Business)

`update_business_metrics()` 가 60초마다 DB 집계 후 갱신합니다.

| 메트릭 이름 | 타입 | 라벨 | 설명 | 갱신 시점 |
|-------------|------|------|------|------------|
| `photo_api_users_total` | Gauge | `status` | 등록 사용자 수. status: total \| active | business_metrics_loop |
| `photo_api_albums_total` | Gauge | `type` | 앨범 수. type: total \| shared (공유 링크 있는 앨범) | 동일 |
| `photo_api_photos_total` | Gauge | — | 전체 사진 수 | 동일 |
| `photo_api_share_links_total` | Gauge | `status` | 공유 링크 수. status: total \| active | 동일 |
| `photo_api_business_new_users_24h` | Gauge | — | 최근 24시간 신규 가입 수 | 동일 |
| `photo_api_business_new_users_7d` | Gauge | — | 최근 7일 신규 가입 수 | 동일 |
| `photo_api_business_avg_albums_per_user` | Gauge | — | 사용자당 평균 앨범 수 | 동일 |
| `photo_api_business_avg_photos_per_album` | Gauge | — | 앨범당 평균 사진 수 | 동일 |
| `photo_api_business_avg_photos_per_user` | Gauge | — | 사용자당 평균 사진 수 | 동일 |
| `photo_api_business_share_rate_percent` | Gauge | — | 공유 링크가 있는 앨범 비율(%) | 동일 |
| `photo_api_business_photos_uploaded_24h` | Gauge | — | 최근 24시간 업로드된 사진 수 | 동일 |
| `photo_api_business_share_links_created_24h` | Gauge | — | 최근 24시간 생성된 공유 링크 수 | 동일 |
| `photo_api_business_total_share_views` | Gauge | — | 공유 링크 조회수 합계 (view_count 합) | 동일 |
| `photo_api_temp_upload_incomplete_after_ttl` | Gauge | — | TTL 만료 후 confirm 되지 않은 임시 URL 발급 건 수 | 동일 (temp_upload 집계) |

---

## 10. Object Storage 사용량

| 메트릭 이름 | 타입 | 라벨 | 설명 | 갱신 시점 |
|-------------|------|------|------|------------|
| `photo_api_object_storage_usage_bytes` | Gauge | — | 전체 OBS 사용량(bytes). 사진 file_size 합계 | update_business_metrics |
| `photo_api_object_storage_usage_by_user_bytes` | Gauge | `user_id` | 사용자별 OBS 사용량(bytes) | 동일 |
| `photo_api_photo_upload_size_total_bytes` | Counter | `user_id` | 사용자별 누적 업로드 용량(bytes). 업로드 시 실시간 증가 | 업로드 confirm 시 `.inc(size)` |

---

## 11. 인증 (Auth)

| 메트릭 이름 | 타입 | 라벨 | 설명 | 갱신 시점 |
|-------------|------|------|------|------------|
| `photo_api_user_registration_total` | Counter | `result` | 회원가입 시도 수. result: success \| failure | 회원가입 엔드포인트 |
| `photo_api_user_login_total` | Counter | `result` | 로그인 시도 수. result: success \| failure | 로그인 엔드포인트 |
| `photo_api_jwt_token_validation_total` | Counter | `result` | JWT 검증 시도 수(Bearer 토큰). result: success \| failure | 보호 라우트 진입 시 |

---

## 12. 커스텀 컬렉터

`/metrics` 스크래핑 시 **커스텀 컬렉터**가 아래 메트릭을 생성합니다. 값은 `update_business_metrics()` 에서 채운 전역 리스트를 기반으로 합니다.

### 12.1 AlbumTop10Collector

| 메트릭 이름 | 타입 | 라벨 | 설명 |
|-------------|------|------|------|
| `photo_api_album_top10_by_photo_count` | Gauge | `rank`, `album_id` | 앨범별 사진 수 Top 10. rank=1이 최다 |
| `photo_api_album_top10_by_storage_bytes` | Gauge | `rank`, `album_id` | 앨범별 이미지 저장 용량(bytes) Top 10 |
| `photo_api_album_top10_by_share_views` | Gauge | `rank`, `album_id` | 앨범별 공유 링크 조회수 Top 10 |

### 12.2 PhotosByTypeCollector

| 메트릭 이름 | 타입 | 라벨 | 설명 |
|-------------|------|------|------|
| `photo_api_photos_total_by_content_type` | Gauge | `content_type` | content_type(MIME)별 총 사진 수 |
| `photo_api_object_storage_usage_by_content_type_bytes` | Gauge | `content_type` | content_type별 총 저장 용량(bytes) |

### 12.3 LogQueueSizeCollector

| 메트릭 이름 | 타입 | 라벨 | 설명 |
|-------------|------|------|------|
| `photo_api_log_queue_size` | Gauge | — | NHN 로거 큐 길이 (높으면 백프레셔) |

---

## 13. DB 연결 풀

정의: `app/database.py`. PostgreSQL/MySQL 사용 시만 의미 있음(SQLite는 NullPool).

| 메트릭 이름 | 타입 | 라벨 | 설명 | 갱신 시점 |
|-------------|------|------|------|------------|
| `photo_api_db_pool_active_connections` | Gauge | — | 현재 존재하는 DB 연결 수 = pool_size + overflow. 체크아웃된 연결 포함 | connect/checkout/checkin 이벤트 시 |
| `photo_api_db_pool_waiting_requests` | Gauge | — | 현재 overflow로 생성된 연결 수 (대기 요청 수 아님) | 동일 |

---

## 14. 헬스체크

정의: `app/routers/health.py`.

| 메트릭 이름 | 타입 | 라벨 | 설명 | 갱신 시점 |
|-------------|------|------|------|------------|
| `photo_api_health_check_status` | Gauge | `check_type` | 헬스체크 결과. 1=healthy, 0=unhealthy. check_type: `fast` \| `detailed` | GET /health, GET /health/detailed 호출 시 |

---

## 15. 앱 식별 (setup 시 등록)

`setup_prometheus(app)` 호출 시 한 번 등록됩니다.

| 메트릭 이름 | 타입 | 라벨 | 설명 |
|-------------|------|------|------|
| `photo_api_app_info` | Gauge | `node`, `app`, `version`, `environment`, `region` | 앱·노드 식별용. 값은 항상 1. 라벨만 사용 |

---

## Circuit Breaker 메트릭

외부 서비스 호출에 Circuit Breaker를 사용할 때 다음 메트릭이 사용됩니다.

| 메트릭 이름 | 타입 | 라벨 | 설명 |
|-------------|------|------|------|
| `photo_api_circuit_breaker_requests_total` | Counter | `service`, `status` | CB 통과 요청 수. status: success \| failure \| rejected |
| `photo_api_circuit_breaker_failures_total` | Counter | `service`, `exception_type` | 예외 타입별 실패 수 |
| `photo_api_circuit_breaker_state_transitions_total` | Counter | `service`, `from_state`, `to_state` | 상태 전이 횟수 |
| `photo_api_circuit_breaker_call_duration_seconds` | Histogram | `service` | CB를 통한 호출 소요 시간(초) |
| `photo_api_circuit_breaker_state` | Gauge | `service` | 현재 상태. 0=CLOSED, 1=OPEN, 2=HALF_OPEN |
| `photo_api_circuit_breaker_consecutive_failures` | Gauge | `service` | 연속 실패 횟수 |
| `photo_api_circuit_breaker_last_state_change_timestamp_seconds` | Gauge | `service` | 마지막 상태 전이 시각(Unix 초) |

(정의·갱신: `app/utils/circuit_breaker.py`)

---

## Instrumentator (FastAPI) 메트릭

`prometheus_fastapi_instrumentator`가 자동으로 노출하는 메트릭(접두사는 설정에 따라 다름):

- `http_requests_total` — 라벨: method, handler, status 등
- `http_request_duration_seconds` — 요청 지연 Histogram

이 문서의 “Photo API가 만든 메트릭”에는 위 자동 메트릭은 제외했습니다.

---

## 참고

- **노출**: `GET /metrics` (Instrumentator.expose).
- **갱신 주기**: 비즈니스/풀 메트릭은 60초마다 `business_metrics_loop()` → `update_business_metrics()`.
- **Pushgateway**: `PROMETHEUS_PUSHGATEWAY_URL` 설정 시 주기적으로 위 레지스트리를 Pushgateway로 푸시.
