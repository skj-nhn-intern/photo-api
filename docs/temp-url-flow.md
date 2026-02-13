# Temp URL 업로드 흐름 (Mermaid)

## 전체 시퀀스 (클라이언트 ↔ API ↔ Object Storage)

```mermaid
sequenceDiagram
    participant Client as 클라이언트 (브라우저)
    participant API as Photo API (FastAPI)
    participant DB as DB
    participant Storage as NHN Object Storage (Swift API)

    Note over Client,Storage: 1. 업로드 URL 발급
    Client->>+API: POST /photos/presigned-url<br/>{ album_id, filename, content_type, file_size }<br/>Header: Authorization: Bearer {JWT}
    API->>API: JWT 검증, 파일 크기/타입 검증
    API->>DB: 앨범 존재 및 권한 확인
    API->>DB: Photo 레코드 생성 (pending)<br/>storage_path = image/{album_id}/{uuid}.{ext}
    API->>API: generate_temp_upload_url(path, content_type)<br/>path = /v1/AUTH_{tenant}/{container}/{object_name}<br/>hmac_body = "PUT\n{expires}\n{path}"<br/>sig = HMAC-SHA256(temp_url_key, hmac_body)<br/>url = endpoint + path + ?temp_url_sig=&temp_url_expires=
    API->>DB: 앨범에 photo 추가, commit
    API-->>-Client: 200 { photo_id, upload_url, upload_method: "PUT", upload_headers: { "Content-Type": "image/jpeg" }, expires_in }

    Note over Client,Storage: 2. 브라우저 → Object Storage 직접 업로드 (CORS preflight)
    Client->>Storage: OPTIONS upload_url<br/>(CORS preflight — PUT + Content-Type 이므로 non-simple)
    Storage-->>Client: 200 + CORS 헤더<br/>(X-Container-Meta-Access-Control-Allow-Origin 등)
    Client->>Storage: PUT upload_url<br/>Header: Content-Type (upload_headers)<br/>Body: file binary
    Storage-->>Client: 201 Created (서명·만료 검증 후 저장)

    Note over Client,API: 3. 업로드 완료 확인
    Client->>+API: POST /photos/confirm<br/>{ photo_id }<br/>Header: Authorization: Bearer {JWT}
    API->>DB: photo 조회, 소유권 확인
    API->>Storage: HEAD {container}/{object_name}<br/>X-Auth-Token (IAM)
    Storage-->>API: 200 OK (파일 존재)
    API->>DB: (이미 생성된 photo 유지)
    API-->>-Client: 200 { photo_id, filename, url, message }
```

## 서버 내부: Temp URL 생성 상세

```mermaid
flowchart LR
    subgraph Input
        A[object_name, content_type, expires_in]
    end
    subgraph "generate_temp_upload_url()"
        B["path = /v1/AUTH_{tenant}/{container}/{object_name}"]
        C["expires = now + expires_in (epoch)"]
        D["hmac_body = PUT + newline + expires + newline + path"]
        E["sig = HMAC-SHA256(temp_url_key, hmac_body)"]
        F["url = endpoint + path + ?temp_url_sig=&temp_url_expires="]
        G["return { url, method: PUT, headers: { Content-Type } }"]
    end
    A --> B --> C --> D --> E --> F --> G
```

## 단계별 요약

| 단계 | 주체 | 동작 |
|------|------|------|
| 1 | 클라이언트 | `POST /photos/presigned-url` 로 메타데이터 전달 (JWT 필수) |
| 2 | API | 검증 후 DB에 Photo(pending) 생성, Temp URL 서명 생성 후 반환 |
| 3 | 클라이언트 | Storage로 **OPTIONS** (CORS preflight) → **PUT** + `upload_headers` + 파일 바디 |
| 4 | Storage | `temp_url_sig`, `temp_url_expires` 검증 후 PUT 처리 (컨테이너 CORS 설정 필요) |
| 5 | 클라이언트 | `POST /photos/confirm` 로 완료 알림 |
| 6 | API | Storage에 파일 존재 확인(HEAD) 후 200 반환 |

## 사전 설정 (1회)

Temp URL이 동작하려면 컨테이너에 다음이 필요합니다.

1. **Temp URL Key**  
   `X-Container-Meta-Temp-URL-Key: {key}` (환경변수 `NHN_STORAGE_TEMP_URL_KEY`와 동일)
2. **CORS**  
   `X-Container-Meta-Access-Control-Allow-Origin: *` (또는 허용 오리진)  
   → 브라우저의 OPTIONS preflight가 412가 아닌 200으로 처리되려면 필수입니다.
