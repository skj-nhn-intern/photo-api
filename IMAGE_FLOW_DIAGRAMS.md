# 이미지 업로드 및 조회 흐름 다이어그램

## 1. Presigned URL 방식 업로드 (권장)

```mermaid
sequenceDiagram
    participant Client
    participant API as Photo API Server
    participant DB as Database
    participant OBS as Object Storage
    participant CDN as CDN

    Note over Client,CDN: 1단계: Presigned URL 요청
    Client->>API: POST /photos/presigned-url<br/>(JWT, album_id, filename, content_type, file_size)
    API->>API: JWT 인증 확인
    API->>DB: 앨범 존재 및 권한 확인
    API->>DB: 사진 메타데이터 저장 (pending)
    API->>OBS: Presigned URL 생성 요청
    OBS-->>API: Presigned URL + Headers 반환
    API->>DB: 커밋
    API-->>Client: 200 OK<br/>(photo_id, upload_url, upload_headers)

    Note over Client,OBS: 2단계: 직접 업로드 (서버 경유 없음)
    Client->>OBS: PUT upload_url<br/>(upload_headers + file)
    OBS-->>Client: 200 OK (업로드 완료)

    Note over Client,API: 3단계: 업로드 확인
    Client->>API: POST /photos/confirm<br/>(JWT, photo_id)
    API->>API: JWT 인증 확인
    API->>DB: 사진 메타데이터 조회
    API->>OBS: 파일 존재 확인
    OBS-->>API: 파일 존재 확인됨
    API->>DB: 커밋
    API->>CDN: CDN URL 생성 (선택적)
    CDN-->>API: CDN URL with Auth Token
    API-->>Client: 200 OK<br/>(photo_id, filename, url)
```

## 2. 직접 업로드 방식 (레거시)

```mermaid
sequenceDiagram
    participant Client
    participant API as Photo API Server
    participant DB as Database
    participant OBS as Object Storage
    participant CDN as CDN

    Note over Client,CDN: 직접 업로드 (서버 경유)
    Client->>API: POST /photos/<br/>(JWT, file, album_id, title, description)
    API->>API: JWT 인증 확인
    API->>API: 파일 크기/타입 검증
    API->>DB: 앨범 존재 및 권한 확인
    API->>OBS: 파일 업로드
    OBS-->>API: 업로드 완료
    API->>DB: 사진 메타데이터 저장
    API->>DB: 앨범에 사진 추가
    API->>DB: 커밋
    API->>CDN: CDN URL 생성 (선택적)
    CDN-->>API: CDN URL with Auth Token
    API-->>Client: 201 Created<br/>(photo_id, filename, url)
```

## 3. 인증된 사용자 이미지 조회

```mermaid
sequenceDiagram
    participant Client
    participant API as Photo API Server
    participant DB as Database
    participant CDN as CDN
    participant OBS as Object Storage

    Note over Client,OBS: 이미지 조회 (JWT 필수)
    Client->>API: GET /photos/{id}/image<br/>(Authorization: Bearer {JWT})
    API->>API: JWT 인증 확인
    API->>DB: 사진 조회 + 소유자 확인
    alt 사진 없음 또는 소유자 아님
        API-->>Client: 404 Not Found
    else 사진 존재 및 권한 있음
        alt CDN 설정됨
            API->>CDN: Auth Token URL 생성
            CDN-->>API: CDN URL with Auth Token
            API-->>Client: 302 Found<br/>(Location: CDN URL)
            Client->>CDN: GET CDN URL
            CDN->>CDN: Auth Token 검증
            CDN->>OBS: 파일 요청
            OBS-->>CDN: 파일 반환
            CDN-->>Client: 200 OK (이미지)
        else CDN 미설정
            API->>OBS: 파일 다운로드
            OBS-->>API: 파일 반환
            API-->>Client: 200 OK (이미지 스트림)
        end
    end
```

## 4. 공유 링크를 통한 이미지 조회

```mermaid
sequenceDiagram
    participant Client
    participant API as Photo API Server
    participant DB as Database
    participant CDN as CDN
    participant OBS as Object Storage

    Note over Client,OBS: 공유 링크 이미지 조회 (인증 불필요)
    Client->>API: GET /share/{token}/photos/{id}/image
    API->>DB: 공유 링크 토큰 검증
    alt 토큰 무효/만료
        API-->>Client: 404 Not Found / 410 Gone
    else 토큰 유효
        API->>DB: 앨범 조회
        API->>DB: 사진이 앨범에 포함되어 있는지 확인
        alt 사진이 앨범에 없음
            API-->>Client: 404 Not Found
        else 사진이 앨범에 있음
            alt CDN 설정됨
                API->>CDN: Auth Token URL 생성
                CDN-->>API: CDN URL with Auth Token
                API-->>Client: 302 Found<br/>(Location: CDN URL)
                Client->>CDN: GET CDN URL
                CDN->>CDN: Auth Token 검증
                CDN->>OBS: 파일 요청
                OBS-->>CDN: 파일 반환
                CDN-->>Client: 200 OK (이미지)
            else CDN 미설정
                API->>OBS: 파일 다운로드
                OBS-->>API: 파일 반환
                API-->>Client: 200 OK (이미지 스트림)
            end
        end
    end
```

## 5. 전체 이미지 업로드 및 조회 아키텍처

```mermaid
graph TB
    subgraph "클라이언트"
        Web[웹 브라우저]
        Mobile[모바일 앱]
    end

    subgraph "API 서버"
        API[Photo API<br/>FastAPI]
        Auth[JWT 인증]
        RateLimit[Rate Limiting]
    end

    subgraph "데이터 저장소"
        DB[(PostgreSQL<br/>메타데이터)]
        OBS[Object Storage<br/>파일 저장]
    end

    subgraph "콘텐츠 전송"
        CDN[CDN<br/>Auth Token]
    end

    subgraph "모니터링"
        Prometheus[Prometheus]
        Grafana[Grafana]
        Logs[Log & Crash]
    end

    Web -->|1. 업로드 요청| API
    Mobile -->|1. 업로드 요청| API
    API -->|인증| Auth
    API -->|제한| RateLimit
    API -->|메타데이터| DB
    API -->|Presigned URL| OBS
    Web -->|2. 직접 업로드| OBS
    Mobile -->|2. 직접 업로드| OBS
    API -->|3. 확인| OBS

    Web -->|조회 요청| API
    Mobile -->|조회 요청| API
    API -->|권한 확인| DB
    API -->|CDN URL 생성| CDN
    CDN -->|파일 요청| OBS
    Web -->|이미지 다운로드| CDN
    Mobile -->|이미지 다운로드| CDN

    API -->|메트릭| Prometheus
    Prometheus -->|시각화| Grafana
    API -->|로그| Logs
```

## 6. 업로드 방식 비교

```mermaid
graph LR
    subgraph "Presigned URL 방식 (권장)"
        P1[1. Presigned URL 요청]
        P2[2. 직접 업로드]
        P3[3. 업로드 확인]
        P1 --> P2 --> P3
        P_Adv[장점:<br/>- 서버 부하 감소<br/>- 업로드 속도 향상<br/>- 대역폭 절약]
    end

    subgraph "직접 업로드 방식 (레거시)"
        D1[1. 파일 + 메타데이터 전송]
        D2[2. 서버가 업로드]
        D1 --> D2
        D_Adv[장점:<br/>- 구현 간단<br/>- 단일 요청]
        D_Dis[단점:<br/>- 서버 부하 증가<br/>- 느린 업로드<br/>- 대역폭 소모]
    end
```

## 7. 보안 흐름

```mermaid
sequenceDiagram
    participant User
    participant API as Photo API
    participant DB as Database
    participant CDN as CDN
    participant OBS as Object Storage

    Note over User,OBS: 보안 보장 메커니즘

    rect rgb(255, 240, 240)
        Note over User,API: 인증된 사용자 이미지 접근
        User->>API: GET /photos/{id}/image<br/>(JWT)
        API->>API: JWT 검증
        API->>DB: 사진 소유자 확인
        alt 소유자 아님
            API-->>User: 404 Not Found
        else 소유자
            API->>CDN: Auth Token URL 생성 (120초 유효)
            CDN-->>API: CDN URL with Token
            API-->>User: 302 Redirect
            User->>CDN: GET (Token 포함)
            CDN->>CDN: Token 검증
            CDN->>OBS: 파일 요청
            OBS-->>CDN: 파일 반환
            CDN-->>User: 이미지
        end
    end

    rect rgb(240, 255, 240)
        Note over User,API: 공유 링크 이미지 접근
        User->>API: GET /share/{token}/photos/{id}/image
        API->>DB: 토큰 검증
        alt 토큰 무효/만료
            API-->>User: 404/410
        else 토큰 유효
            API->>DB: 앨범 소속 확인
            alt 다른 앨범 사진
                API-->>User: 404 Not Found
            else 해당 앨범 사진
                API->>CDN: Auth Token URL 생성
                CDN-->>API: CDN URL with Token
                API-->>User: 302 Redirect
                User->>CDN: GET (Token 포함)
                CDN-->>User: 이미지
            end
        end
    end

    rect rgb(240, 240, 255)
        Note over User,OBS: OBS 직접 접근 차단
        User->>OBS: 직접 URL 접근 시도
        OBS-->>User: 403 Forbidden<br/>(CDN Auth Token 없음)
    end
```

## 8. 에러 처리 흐름

```mermaid
flowchart TD
    Start([업로드/조회 시작]) --> Auth{인증 확인}
    Auth -->|실패| AuthError[401 Unauthorized]
    Auth -->|성공| Validate{요청 검증}
    
    Validate -->|파일 크기 초과| SizeError[413 Request Entity Too Large]
    Validate -->|파일 타입 불일치| TypeError[400 Bad Request]
    Validate -->|앨범 없음| AlbumError[404 Not Found]
    Validate -->|통과| Process[처리 시작]
    
    Process --> DB{DB 작업}
    DB -->|실패| DBError[500 Internal Server Error]
    DB -->|성공| Storage{Storage 작업}
    
    Storage -->|업로드 실패| StorageError[500 Internal Server Error]
    Storage -->|파일 없음| NotFoundError[404 Not Found]
    Storage -->|성공| CDN{CDN 설정}
    
    CDN -->|설정됨| CDNGen[CDN URL 생성]
    CDN -->|미설정| Stream[백엔드 스트리밍]
    
    CDNGen -->|성공| Redirect[302 Redirect]
    CDNGen -->|실패| Stream
    Stream --> Success[200 OK]
    Redirect --> Success
    
    AuthError --> End([종료])
    SizeError --> End
    TypeError --> End
    AlbumError --> End
    DBError --> End
    StorageError --> End
    NotFoundError --> End
    Success --> End
```

## 9. 메트릭 수집 포인트

```mermaid
sequenceDiagram
    participant Client
    participant API as Photo API
    participant Metrics as Prometheus Metrics
    participant Prometheus as Prometheus

    Note over Client,Prometheus: 업로드 메트릭 수집
    Client->>API: POST /photos/presigned-url
    API->>Metrics: presigned_url_generation_total<br/>(result: success/failure)
    API->>Metrics: photo_upload_file_size_bytes<br/>(upload_method: presigned)
    
    Client->>API: POST /photos/confirm
    API->>Metrics: photo_upload_confirm_total<br/>(result: success/failure)
    API->>Metrics: photo_upload_total<br/>(upload_method: presigned, result: success/failure)

    Note over Client,Prometheus: 조회 메트릭 수집
    Client->>API: GET /photos/{id}/image
    API->>Metrics: image_access_total<br/>(access_type: authenticated, result: success/denied)
    API->>Metrics: image_access_duration_seconds<br/>(access_type, result)

    Metrics->>Prometheus: 메트릭 노출 (/metrics)
    Prometheus->>Prometheus: 스크래핑 및 저장
```

## 10. 성능 최적화 포인트

```mermaid
graph TB
    subgraph "업로드 최적화"
        P1[Presigned URL 사용]
        P2[직접 업로드]
        P3[서버 부하 감소]
        P1 --> P2 --> P3
    end

    subgraph "조회 최적화"
        C1[CDN 리다이렉트]
        C2[Auth Token 캐싱]
        C3[로드밸런서 우회]
        C1 --> C2 --> C3
    end

    subgraph "데이터베이스 최적화"
        D1[인덱스 활용]
        D2[비동기 쿼리]
        D3[연결 풀링]
        D1 --> D2 --> D3
    end

    subgraph "모니터링"
        M1[메트릭 수집]
        M2[성능 추적]
        M3[병목 지점 식별]
        M1 --> M2 --> M3
    end
```
