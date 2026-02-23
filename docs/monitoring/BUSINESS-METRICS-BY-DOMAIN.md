# 비즈니스 관점 도메인 메트릭

## 개요

Photo API의 **전체 도메인**을 비즈니스 관점에서 바라본 메트릭 정의서입니다. 성장·참여·전환·리텐션 등 의사결정에 활용할 수 있도록 도메인별로 정리했습니다.

**도메인**: 사용자(Auth/User), 앨범(Album), 사진(Photo), 공유(Share), 스토리지(Storage)

**수집 방식**  
- **주기 집계**: `update_business_metrics()`가 60초마다 DB를 조회해 Gauge를 갱신  
- **이벤트 기반**: API 요청 시점에 Counter/Histogram 증가 (가입, 로그인, 업로드, 앨범/공유 작업 등)

---

## 1. 사용자 도메인 (User / Auth)

### 1.1 비즈니스 질문

- 가입 추이는 어떤가? (일/주 단위 신규 가입)
- 로그인 성공률은? (정상 사용 vs 크리덴셔널 문제)
- 전체·활성 회원 수는?

### 1.2 메트릭 목록

| 메트릭명 | 타입 | 라벨/비고 | 수집 방식 | 비즈니스 활용 |
|----------|------|------------|-----------|----------------|
| `photo_api_users_total` | Gauge | `status`: total \| active | 주기 집계 | 회원 수, 활성 비율 |
| `photo_api_business_new_users_24h` | Gauge | — | 주기 집계 | 최근 24시간 신규 가입자 수 |
| `photo_api_business_new_users_7d` | Gauge | — | 주기 집계 | 최근 7일 신규 가입자 수 |
| `photo_api_user_registration_total` | Counter | `result`: success \| failure | 이벤트 | 가입 시도·성공률 |
| `photo_api_user_login_total` | Counter | `result`: success \| failure | 이벤트 | 로그인 시도·성공률 |
| `photo_api_login_duration_seconds` | Histogram | `result` | 이벤트 | 로그인 체감 속도 |

### 1.3 쿼리 예시

```promql
# 가입 성공률 (5분 구간)
sum(rate(photo_api_user_registration_total{result="success"}[5m])) / sum(rate(photo_api_user_registration_total[5m])) * 100

# 로그인 성공률
sum(rate(photo_api_user_login_total{result="success"}[5m])) / sum(rate(photo_api_user_login_total[5m])) * 100

# 활성 회원 비율
photo_api_users_total{status="active"} / photo_api_users_total{status="total"} * 100
```

---

## 2. 앨범 도메인 (Album)

### 2.1 비즈니스 질문

- 사용자당 앨범 수는? (참여도)
- 앨범당 평균 사진 수는? (콘텐츠 밀도)
- 앨범 중 공유 비율은?

### 2.2 메트릭 목록

| 메트릭명 | 타입 | 라벨/비고 | 수집 방식 | 비즈니스 활용 |
|----------|------|------------|-----------|----------------|
| `photo_api_albums_total` | Gauge | `type`: total \| shared | 주기 집계 | 전체/공유 앨범 수 |
| `photo_api_business_avg_albums_per_user` | Gauge | — | 주기 집계 | 사용자당 평균 앨범 수 |
| `photo_api_business_avg_photos_per_album` | Gauge | — | 주기 집계 | 앨범당 평균 사진 수 |
| `photo_api_business_share_rate_percent` | Gauge | — | 주기 집계 | 공유 앨범 비율(%) |
| `photo_api_album_operations_total` | Counter | `operation`, `result` | 이벤트 | 생성/수정/삭제 성공·실패 |
| `photo_api_album_photo_operations_total` | Counter | `operation`, `result` | 이벤트 | 사진 추가/제거 성공·실패 |

### 2.3 쿼리 예시

```promql
# 공유 앨범 비율 (이미 % 로 나옴)
photo_api_business_share_rate_percent

# 앨범 생성 성공률 (5분)
sum(rate(photo_api_album_operations_total{operation="create",result="success"}[5m])) / sum(rate(photo_api_album_operations_total{operation="create"}[5m])) * 100
```

---

## 3. 사진 도메인 (Photo)

### 3.1 비즈니스 질문

- 사진 수 추이·사용자당 평균 사진 수는?
- 최근 24시간 업로드 활동은?
- 업로드 성공률·Presigned URL 성공률은?

### 3.2 메트릭 목록

| 메트릭명 | 타입 | 라벨/비고 | 수집 방식 | 비즈니스 활용 |
|----------|------|------------|-----------|----------------|
| `photo_api_photos_total` | Gauge | — | 주기 집계 | 전체 사진 수 |
| `photo_api_business_avg_photos_per_user` | Gauge | — | 주기 집계 | 사용자당 평균 사진 수 |
| `photo_api_business_photos_uploaded_24h` | Gauge | — | 주기 집계 | 최근 24h 업로드 수 |
| `photo_api_photo_upload_total` | Counter | `upload_method`, `result` | 이벤트 | 업로드 시도·성공률 |
| `photo_api_presigned_url_generation_total` | Counter | `result` | 이벤트 | Presigned URL 발급 성공률 |
| `photo_api_photo_upload_confirm_total` | Counter | `result` | 이벤트 | 업로드 완료 확인 성공률 |
| `photo_api_photo_upload_file_size_bytes` | Histogram | `upload_method` | 이벤트 | 업로드 파일 크기 분포 |
| `photo_api_photo_upload_size_total_bytes` | Counter | `user_id` | 이벤트 | 사용자별 누적 업로드 용량 |
| `photo_api_image_access_total` | Counter | `access_type`, `result` | 이벤트 | 이미지 조회(인증/공유)·성공률 |

### 3.3 쿼리 예시

```promql
# 업로드 성공률 (presigned)
sum(rate(photo_api_photo_upload_total{upload_method="presigned",result="success"}[5m])) / sum(rate(photo_api_photo_upload_total{upload_method="presigned"}[5m])) * 100

# Presigned URL 발급 성공률
sum(rate(photo_api_presigned_url_generation_total{result="success"}[5m])) / sum(rate(photo_api_presigned_url_generation_total[5m])) * 100

# 이미지 조회 성공률 (인증 사용자)
sum(rate(photo_api_image_access_total{access_type="authenticated",result="success"}[5m])) / sum(rate(photo_api_image_access_total{access_type="authenticated"}[5m])) * 100
```

---

## 4. 공유 도메인 (Share)

### 4.1 비즈니스 질문

- 공유 링크 수·활성 링크 비율은?
- 최근 24시간 공유 링크 생성 수는?
- 공유 링크를 통한 총 조회수는?
- 공유 링크 생성 성공률은?

### 4.2 메트릭 목록

| 메트릭명 | 타입 | 라벨/비고 | 수집 방식 | 비즈니스 활용 |
|----------|------|------------|-----------|----------------|
| `photo_api_share_links_total` | Gauge | `status`: total \| active | 주기 집계 | 전체/활성 공유 링크 수 |
| `photo_api_business_share_links_created_24h` | Gauge | — | 주기 집계 | 최근 24h 생성 수 |
| `photo_api_business_total_share_views` | Gauge | — | 주기 집계 | 공유 링크 총 조회수 |
| `photo_api_share_link_creation_total` | Counter | `result` | 이벤트 | 공유 링크 생성 성공·실패 |
| `photo_api_share_link_access_total` | Counter | `token_status`, `result` | 이벤트 | 링크 접근(유효/무효/만료)·결과 |
| `photo_api_share_link_image_access_total` | Counter | `token_status`, `photo_in_album` | 이벤트 | 공유로 이미지 조회 수 |

### 4.3 쿼리 예시

```promql
# 활성 공유 링크 비율
photo_api_share_links_total{status="active"} / photo_api_share_links_total{status="total"} * 100

# 공유 링크 생성 성공률
sum(rate(photo_api_share_link_creation_total{result="success"}[5m])) / sum(rate(photo_api_share_link_creation_total[5m])) * 100
```

---

## 5. 스토리지 도메인 (Storage / 용량)

### 5.1 비즈니스 질문

- 전체·사용자별 저장 용량은?
- 용량 급증 시점·주체는?

### 5.2 메트릭 목록

| 메트릭명 | 타입 | 라벨/비고 | 수집 방식 | 비즈니스 활용 |
|----------|------|------------|-----------|----------------|
| `photo_api_object_storage_usage_bytes` | Gauge | — | 주기 집계 | 전체 Object Storage 사용량 |
| `photo_api_object_storage_usage_by_user_bytes` | Gauge | `user_id` | 주기 집계 | 사용자별 사용량 |
| `photo_api_photo_upload_size_total_bytes` | Counter | `user_id` | 이벤트 | 사용자별 누적 업로드 용량(추이) |

### 5.3 쿼리 예시

```promql
# 전체 사용량 (GB)
photo_api_object_storage_usage_bytes / 1024 / 1024 / 1024

# 사용자별 최근 1시간 업로드 용량 (rate)
sum by (user_id) (rate(photo_api_photo_upload_size_total_bytes[1h])) * 3600
```

---

## 6. 도메인별 요약표

| 도메인 | 성장 지표 | 참여/활동 지표 | 품질/전환 지표 |
|--------|-----------|----------------|----------------|
| **사용자** | new_users_24h/7d, users_total | user_login_total | registration/login 성공률 |
| **앨범** | albums_total | avg_albums_per_user, album_operations | album create 성공률 |
| **사진** | photos_total, photos_uploaded_24h | avg_photos_per_user/album, image_access | upload/presigned/confirm 성공률 |
| **공유** | share_links_total, share_links_created_24h | total_share_views | share_link_creation 성공률, access result |
| **스토리지** | object_storage_usage_bytes | usage_by_user, upload_size_total | — |

---

## 7. 대시보드 제안 (비즈니스 KPI)

### Row 1: 성장 요약

- **Stat**: `photo_api_users_total{status="total"}`, `photo_api_photos_total`, `photo_api_albums_total`
- **Stat**: `photo_api_business_new_users_24h`, `photo_api_business_new_users_7d`
- **Stat**: `photo_api_business_photos_uploaded_24h`, `photo_api_business_share_links_created_24h`

### Row 2: 참여·품질

- **Stat**: `photo_api_business_avg_albums_per_user`, `photo_api_business_avg_photos_per_user`, `photo_api_business_avg_photos_per_album`
- **Stat**: `photo_api_business_share_rate_percent`, `photo_api_business_total_share_views`
- **Time series**: 가입/로그인 성공률 (rate 기반)

### Row 3: 전환·성공률

- **Time series**: `photo_api_user_registration_total`, `photo_api_user_login_total` (rate, result별)
- **Time series**: `photo_api_photo_upload_total`, `photo_api_share_link_creation_total` (rate, result별)
- **Time series**: `photo_api_presigned_url_generation_total`, `photo_api_photo_upload_confirm_total` (rate, result별)

### Row 4: 스토리지

- **Stat**: `photo_api_object_storage_usage_bytes` (GB)
- **Table**: `photo_api_object_storage_usage_by_user_bytes` 상위 N명

---

## 8. 수집 주기·구현 위치

| 구분 | 주기/트리거 | 구현 위치 |
|------|-------------|-----------|
| 주기 집계 Gauge | 60초 | `app.utils.prometheus_metrics.update_business_metrics()` |
| 가입/로그인 Counter | 요청 시 | `app.routers.auth` |
| 앨범/사진/공유 Counter·Histogram | 요청 시 | 각 라우터(albums, photos, share) 및 서비스 레이어 |

---

## 9. 관련 문서

- **전체 모니터링 지표·알림**: `HA_MONITORING_METRICS.md`
- **대시보드·시각화**: `docs/monitoring/SERVICE-MONITORING-DASHBOARD.md`
