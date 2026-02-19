# 이벤트 설계: 액션만, 결과는 level로

**작성일**: 2026-02

- **event** = 무엇에 대한 로그인지 (도메인 **액션**만)
- **level** = 결과/심각도 (INFO=정상, WARNING=주의, ERROR=실패)

성공/실패는 이벤트 이름에 넣지 않고, **level**과 **message**로만 구분합니다.

---

## 1. 공유(Share)

| 이벤트 | 의미 | level 예시 |
|--------|------|------------|
| `share_link_create` | 공유 링크 생성 | INFO=성공, (WARNING=검증 실패 시 라우터에서) |
| `share_access` | 공유 링크 접근 | WARNING=만료/비활성 접근 거부 |
| `share_stream` | 공유 앨범 사진 스트리밍 | ERROR=스트리밍 실패 |

---

## 2. 사진(Photo)

| 이벤트 | 의미 | level 예시 |
|--------|------|------------|
| `photo_upload` | 사진 업로드 | INFO=성공, ERROR=실패 |
| `photo_presigned` | Presigned(Temp) URL 발급 | INFO=성공, ERROR=실패 |
| `photo_upload_confirm` | 클라이언트 업로드 완료 확인 | INFO=성공, ERROR=실패(파일 없음 등) |
| `photo_stream` | 이미지 스트리밍 | ERROR=실패 |
| `photo_download` | 이미지 다운로드 | ERROR=실패 |
| `photo_delete` | 스토리지에서 사진 삭제 | ERROR=삭제 실패(DB 삭제는 완료된 경우) |

---

## 3. 스토리지(Storage)

| 이벤트 | 의미 | level |
|--------|------|-------|
| `storage_auth` | IAM/스토리지 인증 | ERROR |
| `storage_container_create` | 컨테이너 생성 | ERROR |
| `storage_container_check` | 컨테이너 존재 확인 | ERROR |
| `storage_container_ensure` | 컨테이너 ensure 예외 | ERROR |
| `storage_upload` | 파일 업로드 | ERROR |
| `storage_download` | 파일 다운로드 | ERROR |
| `storage_delete` | 파일 삭제 | ERROR |
| `storage_exists` | 파일 존재 확인 | ERROR |
| `storage_presigned` | Presigned POST 생성 | ERROR |

---

## 4. CDN

| 이벤트 | 의미 | level 예시 |
|--------|------|------------|
| `cdn_token` | CDN Auth Token 발급/사용 | ERROR=API 실패, WARNING=실패 후 백엔드 스트리밍 fallback |
| `cdn_obs_fallback` | (레거시) OBS URL 반환 | WARNING — 보안 주의 |

---

## 5. 재시도(Retry)

- **이벤트**: `retry`
- **재시도 대상**: `retry_target` 필드 (예: `"storage.upload"`, `"cdn.token"`)

---

## 6. Loki/대시보드 쿼리 예시

- **액션별 실패 건수**  
  `{job="photo-api"} | json | event="photo_upload" | level="ERROR"`
- **액션별 성공 건수**  
  `{job="photo-api"} | json | event="photo_upload" | level="INFO"`
- **서비스(Image) 이벤트만**  
  `event=~"photo_.*"`
- **서비스(Share) 이벤트만**  
  `event=~"share_.*"`
