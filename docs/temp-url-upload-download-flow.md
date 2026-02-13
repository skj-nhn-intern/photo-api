# Temp URL 파일 업로드 및 다운로드 흐름도

현재 프로젝트에서 구현된 **Swift Temp URL 기반 업로드**와 **이미지/파일 다운로드** 흐름입니다.

- **업로드**: Swift Temp URL (`temp_url_sig`, `temp_url_expires`) 사용 — 클라이언트가 Object Storage에 직접 PUT
- **다운로드**: Temp URL 미사용. API가 JWT로 권한 확인 후 **CDN Auth Token 리다이렉트** 또는 **백엔드 스트리밍**으로 제공

## Mermaid 파일 목록

| 파일 | 설명 |
|------|------|
| [temp-url-upload-sequence.mmd](./temp-url-upload-sequence.mmd) | Temp URL 업로드 전체 시퀀스 (클라이언트 ↔ API ↔ Storage) |
| [temp-url-upload-internal.mmd](./temp-url-upload-internal.mmd) | 서버 내부 Temp URL 생성 상세 (generate_temp_upload_url) |
| [download-image-sequence.mmd](./download-image-sequence.mmd) | 이미지 보기 GET /photos/{id}/image 시퀀스 (CDN/스트리밍 분기) |
| [download-attachment-sequence.mmd](./download-attachment-sequence.mmd) | 파일 다운로드 GET /photos/{id}/download 시퀀스 |
| [upload-download-overview.mmd](./upload-download-overview.mmd) | 업로드·다운로드 통합 플로우차트 |

Mermaid Live Editor(https://mermaid.live) 또는 VS Code Mermaid 확장으로 `.mmd` 파일을 열어 다이어그램을 확인할 수 있습니다.

---

## 단계별 요약

| 구분 | 단계 | 주체 | 동작 |
|------|------|------|------|
| **업로드** | 1 | 클라이언트 | `POST /photos/presigned-url` (JWT, album_id, filename, content_type, file_size) |
| | 2 | API | 검증 후 DB에 Photo(pending) 생성, `generate_temp_upload_url()` 로 Swift Temp URL 생성 후 반환 |
| | 3 | 클라이언트 | Storage로 **OPTIONS** (CORS) → **PUT** + upload_headers + 파일 바디 |
| | 4 | Storage | `temp_url_sig`, `temp_url_expires` 검증 후 PUT 처리 |
| | 5 | 클라이언트 | `POST /photos/confirm` (photo_id) |
| | 6 | API | `file_exists(HEAD)` 로 저장소 확인 후 200 |
| **다운로드** | 1 | 클라이언트 | `GET /photos/{id}/image` 또는 `GET /photos/{id}/download` (JWT) |
| | 2 | API | JWT 검증, photo 조회 |
| | 3a | API | 이미지 + CDN 설정 시 → 302 CDN Auth Token URL |
| | 3b | API | CDN 없거나 download → `download_file()` 로 Storage에서 조회 후 스트리밍/첨부 반환 |

## Temp URL 업로드 사전 설정 (1회)

- **Temp URL Key**: 컨테이너에 `X-Container-Meta-Temp-URL-Key: {key}` 설정 (환경변수 `NHN_STORAGE_TEMP_URL_KEY`와 동일)
- **CORS**: `X-Container-Meta-Access-Control-Allow-Origin: *` (또는 허용 오리진) — 브라우저 OPTIONS preflight가 200으로 처리되도록 필요
