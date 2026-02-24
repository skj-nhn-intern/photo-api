# Temp URL 업로드 탐지 및 집계

Temp URL( presigned URL ) 발급부터 만료까지의 생명주기를 **DB에만** 기록하고, **TTL 만료 후에도 완료되지 않은 건**을 집계하는 방법을 설명합니다.

---

## 1. 구조 요약

| 시점 | 동작 | DB |
|------|------|-----|
| **1. URL 발급 시** | `POST /photos/presigned-url` 성공 | `temp_upload_records`에 insert: `upload_id`(=photo_id), `album_id`, `user_id`, `issued_at`, `expires_at`, `completed_at=NULL` |
| **2. 업로드 완료 시** | `POST /photos/confirm` 성공 | 해당 `upload_id`의 `completed_at` 갱신 |
| **3. TTL 만료 후** | (별도 조회/배치) | `expires_at < now()` 이고 `completed_at IS NULL` 인 행 → **미완료**로 집계 |

- 모든 기록과 집계는 **DB만** 사용합니다.

---

## 2. DB 스키마 (`temp_upload_records`)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `upload_id` | PK, FK(photos.id) | presigned 발급 시 생성된 photo_id와 동일 |
| `album_id` | int, index | 앨범 ID |
| `user_id` | int, FK(users.id), index | 유저 ID |
| `issued_at` | datetime, index | URL 발급 시각 |
| `expires_at` | datetime, index | URL 만료 시각 (발급 시각 + TTL) |
| `completed_at` | datetime, nullable | 업로드 완료 시각. NULL이면 미완료 |

---

## 3. 어떻게 집계하는지

### 3.1. “TTL 만료 후 미완료” 정의

- **조건**: `expires_at < 현재시각` 이고 `completed_at IS NULL`
- 즉, Temp URL을 발급받았지만 만료 시점이 지났고, 그 사이에 **`POST /photos/confirm`**을 호출하지 않은 건입니다. 집계는 **`GET /photos/upload-tracking`** 또는 SQL/스크립트로 수행합니다.

### 3.2. Prometheus 메트릭 (미완료 건수)

- **메트릭 이름**: `photo_api_temp_upload_incomplete_after_ttl` (Gauge)
- **의미**: TTL 만료 후 `completed_at`이 null인 건 수. 60초마다 `temp_upload_records` 테이블만 조회해 갱신.
- **노출**: `GET /metrics`. Prometheus 스크래핑 후 Grafana/알람에서 사용.

### 3.3. 로그로 lifecycle 추적

- presigned 발급·confirm 성공/실패 시 로그에 **upload_id**(= photo_id), **user_id**, **event** 가 남음.
- 로그 수집(Loki 등)에서 `upload_id` 또는 `event=photo_presigned|photo_upload_confirm` 로 필터해 추적 가능.

### 3.4. API로 집계

```http
GET /photos/upload-tracking
Authorization: Bearer <JWT>
```

응답: `total_count`, `by_user_id`, `by_album_id`, `sample_records` (TTL 만료 후 미확인 건)

### 3.5. SQL로 직접 집계

DB에서 직접 조회할 때는 아래와 같이 사용합니다.

**전체 미완료 건수:**

```sql
SELECT COUNT(*) AS incomplete_count
FROM temp_upload_records
WHERE expires_at < NOW()
  AND completed_at IS NULL;
```

**user_id별 미완료 건수:**

```sql
SELECT user_id, COUNT(*) AS incomplete_count
FROM temp_upload_records
WHERE expires_at < NOW()
  AND completed_at IS NULL
GROUP BY user_id;
```

**album_id별 미완료 건수:**

```sql
SELECT album_id, COUNT(*) AS incomplete_count
FROM temp_upload_records
WHERE expires_at < NOW()
  AND completed_at IS NULL
GROUP BY album_id;
```

**특정 기간 내 발급된 건 중 미완료 (예: 오늘 발급 건):**

```sql
SELECT upload_id, user_id, album_id, issued_at, expires_at
FROM temp_upload_records
WHERE issued_at >= CURRENT_DATE
  AND expires_at < NOW()
  AND completed_at IS NULL
ORDER BY expires_at;
```

### 3.6. 배치/스케줄러로 주기 집계

- Cron 등으로 위 SQL을 주기 실행해 수치를 로그/알람/통계 저장소에 적재할 수 있습니다.
- 필요하면 `app.services.temp_upload_tracking.aggregate_incomplete_after_ttl()`를 호출하는 별도 스크립트를 만들어, 기간(`now`)이나 `limit`을 인자로 주어 집계할 수도 있습니다.

### 3.7. 실무에서 흔히 쓰는 방식 (이벤트 기반 제외)

| 방식 | 설명 |
|------|------|
| **Cron + 스크립트** | 서버/컨테이너에 cron 등록 → 주기적으로 `curl GET /photos/upload-tracking` 또는 위 SQL 실행 → 결과를 로그/파일/메트릭 수집기로 전달. 가장 흔함. |
| **Prometheus 스크래핑** | 앱이 60초마다 `photo_api_temp_upload_incomplete_after_ttl` Gauge 갱신. `/metrics` 스크래핑. **(구현됨)** |
| **클라우드 스케줄러** | AWS EventBridge, GCP Cloud Scheduler 등으로 “N분마다 이 URL 호출” 설정. Cron과 동일한 역할. |
| **대시보드 on-demand** | Grafana 등에서 “이 패널은 이 API 호출”로 설정해, 화면 열 때마다 `GET /photos/upload-tracking` 호출. 자동 주기는 없고 필요할 때만. |

이벤트 기반(메시지 큐, 웹훅 등)을 쓰지 않으면 위처럼 **스케줄/폴링**으로 돌리는 경우가 대부분이다.

---

## 4. 플로우 다이어그램

**업로드 플로우** (클라이언트: presigned 발급 → OBS 업로드 → confirm)

```
[클라이언트]                    [Photo API]                    [DB]
     |                               |                           |
     | POST /photos/presigned-url    |                           |
     |------------------------------>|                           |
     |                               | record_issued(...)        |
     |                               |-------------------------->| INSERT
     | PresignedUrlResponse          |<--------------------------|
     |<------------------------------|                           |
     |                               |                           |
     | PUT to Temp URL (OBS 직접)    |                           |
     |==============================>| (OBS)                     |
     |                               |                           |
     | POST /photos/confirm           |                           |
     |------------------------------>| mark_completed(upload_id) |
     |                               |-------------------------->| UPDATE
     | ConfirmResponse               |<--------------------------|
     |<------------------------------|                           |
```

**집계** (필요할 때만 호출)

- **기본적으로 자동 실행되는 건 없음.** 이 API는 그냥 HTTP 엔드포인트라서, 호출하는 쪽을 **직접** 정해야 함.
- 예: 사람이 `curl`/Postman으로 호출, 또는 **Cron**에서 `curl` 스크립트 실행, 또는 **Prometheus/Grafana** 등 모니터링에서 HTTP로 주기 수집.

```
[호출하는 쪽]                    [Photo API]                    [DB]
 (curl / Cron 스크립트 / 모니터링 등)
     |                               |                           |
     | GET /photos/upload-tracking    |                           |
     |------------------------------>| aggregate_incomplete_...  |
     |                               |-------------------------->| SELECT (expires_at < now, completed_at IS NULL)
     | { total_count, by_user_id, ... }                          |
     |<------------------------------|                           |
```

---

## 5. 요약

1. **URL 발급 시** → `upload_id`, 앨범ID, 유저ID, 발급시각(및 만료시각)을 **DB에 기록**합니다.
2. **업로드 완료 시** → `upload_id`에 대해 **완료 처리**(DB `completed_at` 갱신).
3. **TTL 만료 후** → `expires_at < now()` 이고 `completed_at IS NULL` 인 건을 **미완료로 집계**하며, **`GET /photos/upload-tracking`** 또는 SQL/스크립트로 조회합니다.

이 구조로 Temp URL 발급 대비 실제 완료 비율, 유저/앨범별 이탈 추이 등을 일관되게 집계할 수 있습니다.
