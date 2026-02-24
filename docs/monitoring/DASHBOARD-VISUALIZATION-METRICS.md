# 대시보드 시각화 메트릭 가이드

아래 시각화 항목별 PromQL·메트릭·패널 설정 요약입니다.

---

## 인증·사용자

| 시각화 항목 | PromQL / 메트릭 | 시각화 | Unit |
|-------------|------------------|--------|------|
| **로그인 성공률** | `sum(rate(photo_api_user_login_total{result="success"}[5m])) / sum(rate(photo_api_user_login_total[5m])) * 100` | Stat / Time series | percent (0-100) |
| **JWT 접근률** | `sum(rate(photo_api_jwt_token_validation_total[5m])) * 60` (분당 검증 시도 수) | Time series | reqm |
| **JWT 발급률** | `sum(rate(photo_api_user_login_total{result="success"}[5m])) * 60` | Time series | reqm |
| **회원수 추이** | `photo_api_users_total{status="total"}` (Gauge, 주기 갱신) | Time series | short |
| **JWT 토큰 접근·발급 성공률** | 접근: `sum(rate(photo_api_jwt_token_validation_total{result="success"}[5m])) / sum(rate(photo_api_jwt_token_validation_total[5m])) * 100` / 발급: 로그인 성공률과 동일 | Stat | percent (0-100) |

---

## 이미지 업로드·다운로드·접근

| 시각화 항목 | PromQL / 메트릭 | 시각화 | Unit |
|-------------|------------------|--------|------|
| **이미지 업로드 요청량** | `sum(rate(photo_api_photo_upload_total[5m])) * 60` (분당) 또는 성공만: `sum(rate(photo_api_photo_upload_total{result="success"}[5m])) * 60` | Time series | reqm |
| **이미지 다운로드(접근) 요청량** | `sum(rate(photo_api_image_access_total[5m])) * 60` (분당) | Time series | reqm |
| **이미지 접근 시간** | `histogram_quantile(0.95, sum(rate(photo_api_image_access_duration_seconds_bucket[5m])) by (le, access_type))` (P95) 또는 `sum(rate(photo_api_image_access_duration_seconds_sum[5m])) / sum(rate(photo_api_image_access_duration_seconds_count[5m]))` (평균) | Time series | s |

---

## 앨범·공유

| 시각화 항목 | PromQL / 메트릭 | 시각화 | Unit |
|-------------|------------------|--------|------|
| **앨범 생성량** | `sum(rate(photo_api_album_operations_total{operation="create", result="success"}[5m])) * 60` (분당) 또는 `increase(photo_api_album_operations_total{operation="create", result="success"}[1h])` | Time series | reqm / short |
| **용량별 앨범 접근 시간** | P95: `histogram_quantile(0.95, sum(rate(photo_api_album_access_duration_seconds_bucket[5m])) by (le, size_bucket, access_type))` / 평균: `sum(rate(photo_api_album_access_duration_seconds_sum[5m])) by (size_bucket, access_type) / sum(rate(photo_api_album_access_duration_seconds_count[5m])) by (size_bucket, access_type)` (size_bucket: empty=0장, small=1–10, medium=11–50, large=51+) | **Heatmap** (권장) 또는 Time series | s |
| ↳ Heatmap 설정 | 쿼리: `sum(increase(photo_api_album_access_duration_seconds_bucket[1m])) by (le, size_bucket)` (시간×레이트 구간 분포). 또는 P95 쿼리로 시계열 후 패널 유형을 Heatmap으로 두고, Y축에 `size_bucket`/`access_type` 사용. | Heatmap | — |
| **앨범별 이미지 사용량 Top 10** | `photo_api_album_top10_by_photo_count` (rank, album_id) | Table / Bar gauge | short |
| **앨범별 사용한 이미지 총량 Top 10** | `photo_api_album_top10_by_storage_bytes` (rank, album_id) | Table / Bar gauge | bytes (IEC) |
| **공유 앨범 생성량** | 공유 링크 생성으로 대체: `sum(rate(photo_api_share_link_creation_total{result="success"}[5m])) * 60` | Time series | reqm |
| **공유 링크 생성 성공량** | `sum(rate(photo_api_share_link_creation_total{result="success"}[5m])) * 60` (분당) 또는 `increase(photo_api_share_link_creation_total{result="success"}[1h])` | Time series | reqm / short |
| **공유 링크 (valid/invalid) 접속량** | valid: `sum(rate(photo_api_share_link_access_total{token_status="valid"}[5m])) * 60` / invalid: `sum(rate(photo_api_share_link_access_total{token_status="invalid"}[5m])) * 60` / expired: `sum(rate(photo_api_share_link_access_total{token_status="expired"}[5m])) * 60` | Time series | reqm |
| **접속량이 많은 앨범 Top 10** | 실시간: `topk(10, sum by (album_id) (rate(photo_api_share_link_access_by_album_total[5m])) * 60)` (분당) / 스냅샷: `photo_api_album_top10_by_share_views` (rank, album_id) | Time series·Table / Bar gauge | reqm·short |

---

## CDN·OBS

| 시각화 항목 | PromQL / 메트릭 | 시각화 | Unit |
|-------------|------------------|--------|------|
| **CDN Auth Token 요청량** | `sum(rate(photo_api_cdn_auth_token_requests_total[5m])) * 60` (분당) / 성공률: `sum(rate(photo_api_cdn_auth_token_requests_total{result="success"}[5m])) / sum(rate(photo_api_cdn_auth_token_requests_total[5m])) * 100` | Time series / Stat | reqm / percent |
| **OBS Temp URL(Presigned) 요청량** | `sum(rate(photo_api_presigned_url_generation_total[5m])) * 60` (분당) | Time series | reqm |

---

## Object Storage 사용량·추이

| 시각화 항목 | PromQL / 메트릭 | 시각화 | Unit |
|-------------|------------------|--------|------|
| **갑자기 OBS 사용량이 늘었을 때, 누가 많이 올렸나?** | 사용자별 누적 업로드 용량(기간): `topk(10, increase(photo_api_photo_upload_size_total_bytes[1h]))` 또는 현재 사용자별 사용량: `photo_api_object_storage_usage_by_user_bytes` | Table / Time series | bytes (IEC) |
| **OBS에 업로드한 총 용량 추이** | `increase(photo_api_photo_upload_size_total_bytes[1h])` (1h 구간 증분) 또는 `sum(photo_api_photo_upload_size_total_bytes)` (누적, Grafana에서 시계열로) | Time series | bytes (IEC) |

**참고**: `photo_api_photo_upload_size_total_bytes`는 라벨 `user_id`별 Counter이므로, 총량은 `sum(increase(photo_api_photo_upload_size_total_bytes[범위]))`로 구간별 업로드 용량을 볼 수 있습니다.

---

## 메트릭 목록 (추가·보완된 것)

| 메트릭 이름 | 유형 | 용도 |
|-------------|------|------|
| `photo_api_user_login_total` | Counter (result) | 로그인 성공률, JWT 발급률 |
| `photo_api_jwt_token_validation_total` | Counter (result) | JWT 접근률, 접근 성공률 |
| `photo_api_users_total` | Gauge (status) | 회원수 추이 |
| `photo_api_photo_upload_total` | Counter (upload_method, result) | 이미지 업로드 요청량 |
| `photo_api_image_access_total` | Counter (access_type, result) | 이미지 다운로드(접근) 요청량 |
| `photo_api_image_access_duration_seconds` | Histogram | 이미지 접근 시간 |
| `photo_api_album_operations_total` | Counter (operation, result) | 앨범 생성량 |
| `photo_api_album_access_duration_seconds` | Histogram (size_bucket, access_type) | 용량별 앨범 접근 시간 |
| `photo_api_album_top10_by_photo_count` | Gauge (rank, album_id) | 앨범별 이미지 개수 Top 10 |
| `photo_api_album_top10_by_storage_bytes` | Gauge (rank, album_id) | 앨범별 이미지 총량 Top 10 |
| `photo_api_album_top10_by_share_views` | Gauge (rank, album_id) | 앨범별 공유 조회수 Top 10 |
| `photo_api_cdn_auth_token_requests_total` | Counter (result) | CDN Auth Token 요청량 |
| `photo_api_presigned_url_generation_total` | Counter (result) | OBS Presigned(임시) URL 요청량 |
| `photo_api_share_link_creation_total` | Counter (result) | 공유 링크 생성 성공량 |
| `photo_api_share_link_access_total` | Counter (token_status, result) | 공유 링크 valid/invalid 접속량 |
| `photo_api_share_link_access_by_album_total` | Counter (album_id) | 앨범별 공유 접속량(Top 10) |
| `photo_api_photo_upload_size_total_bytes` | Counter (user_id) | 사용자별·총 OBS 업로드 용량 추이 |
| `photo_api_object_storage_usage_by_user_bytes` | Gauge (user_id) | 사용자별 현재 OBS 사용량 |
| `photo_api_object_storage_usage_bytes` | Gauge | 전체 OBS 사용량 |
