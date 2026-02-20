# 이미지 업로드·다운로드·조회 흐름 및 보안 설명

## Mermaid 다이어그램

다이어그램 파일: [image-upload-download-view.mmd](./image-upload-download-view.mmd)

- **1. 이미지 업로드 (Presigned URL)** — 권장 방식. 클라이언트가 API를 거치지 않고 Object Storage에 직접 PUT.
- **2. 이미지 업로드 (레거시)** — 파일 전체가 API를 경유하는 방식.
- **3. 이미지 조회** — `GET /photos/{id}/image` (JWT 필수 → 소유자 확인 → CDN 302 또는 백엔드 스트리밍).
- **4. 이미지 다운로드** — `GET /photos/{id}/download` (JWT 필수 → 첨부 파일로 반환).
- **5. 전체 아키텍처** — 업로드/조회 시 데이터 경로 요약.

Mermaid 뷰어(VSCode 확장, GitHub, GitLab 등)에서 `.mmd` 파일을 열어 시퀀스/플로우 차트를 확인할 수 있습니다.

---

## 왜 이 방식이 보안에 강한가?

### 1. **인증·인가가 모든 접근 앞단에 있음**

- **이미지 조회/다운로드**: `GET /photos/{id}/image`, `GET /photos/{id}/download` 는 모두 **JWT 필수**.
- API에서 `get_photo_by_id(photo_id, user_id)` 로 **해당 사진의 소유자만** 허용합니다.
- 따라서 “링크만 알면 누구나 본다”가 아니라, **로그인한 사용자 중 소유자만** 이미지를 볼 수 있습니다.

### 2. **Object Storage(OBS) URL을 절대 노출하지 않음**

- 클라이언트에는 **OBS 원본 URL이 전혀 전달되지 않습니다**.
- 이미지 URL은 항상 **API 경로** (`/photos/{id}/image`) 또는 **CDN Auth Token이 붙은 CDN URL**만 반환됩니다.
- 따라서 OBS 버킷이 public이어도, OBS URL을 알 수 없어서 **직접 접근이 불가능**합니다.

### 3. **CDN Auth Token으로 일회성·단기 접근**

- 이미지 보기 시 CDN을 쓰면, API가 **짧은 유효기간**의 CDN Auth Token이 포함된 URL로만 302 리다이렉트합니다.
- 토큰이 없거나 만료되면 CDN이 **403 등으로 접근을 거부**합니다.
- 그래서 “이미지 URL을 복사해서 다른 사람에게 넘겨도” 시간이 지나면 더 이상 보이지 않고, **영구적인 공개 링크가 되지 않습니다**.

### 4. **업로드도 인증·검증 후에만 완료**

- **Presigned URL**: `POST /photos/presigned-url` 은 JWT로 사용자를 확인하고, 앨범 소유권을 검사한 뒤에만 Temp URL을 발급합니다.
- 업로드 완료 후 `POST /photos/confirm` 에서 **실제로 OBS에 파일이 존재하는지** 확인한 뒤에만 DB를 확정합니다.
- **레거시 업로드**: 파일이 API를 통과하므로, 크기·Content-Type 제한과 앨범 소유권 검사가 모두 적용됩니다.

### 5. **파일 타입·크기 제한**

- 허용 Content-Type: JPEG, PNG, GIF, WebP, HEIC 등 **이미지 타입만** 허용.
- 파일 크기 상한(예: 10MB)으로 **남용·DoS** 를 완화합니다.

### 6. **저장 경로 예측 어려움**

- 저장 경로에 **UUID 기반 고유 파일명**을 사용해, 다른 사용자 사진을 경로만으로 추측해 접근하기 어렵습니다.

---

## 요약

| 보안 요소 | 적용 방식 |
|----------|-----------|
| 인증 | 모든 이미지 접근에 JWT 필수 |
| 인가 | 소유자만 조회/다운로드 가능 (DB에서 owner_id 검증) |
| URL 비노출 | OBS URL 미반환, API 경로 또는 CDN Token URL만 사용 |
| 단기 토큰 | CDN Auth Token 짧은 유효기간 → 링크 유출 시에도 제한적 피해 |
| 업로드 검증 | Presigned 발급 전 앨범 소유권 확인, confirm 시 OBS 존재 여부 확인 |
| 입력 제한 | 이미지 타입·크기 제한, UUID 파일명 |

이 구조는 “이미지를 누가, 언제, 어떤 경로로만 볼 수 있게 할지”를 API와 DB·CDN이 일관되게 통제하기 때문에 **보안에 강한 설계**라고 볼 수 있습니다.
