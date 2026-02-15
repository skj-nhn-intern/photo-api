# CDN Auth Token을 사용한 보안 이미지 접근

## 문제 상황

- **OBS는 public이어야 CDN을 사용할 수 있음**: CDN이 Object Storage의 파일을 가져오려면 OBS가 public으로 설정되어 있어야 합니다.
- **하지만 public이면 보안 문제**: OBS가 public이면 URL만 알면 누구나 이미지에 접근할 수 있습니다.
- **해결책**: CDN Auth Token을 사용하여 임시 서명된 URL만 생성하고, 짧은 유효기간을 설정합니다.

## 현재 구현 방식

### 1. API 응답 (안전)

**중요**: API는 항상 상대 경로만 반환합니다. OBS URL이나 CDN URL(토큰 포함)은 절대 반환하지 않습니다.

```json
{
  "id": 123,
  "url": "/photos/123/image"  // 토큰 없음, OBS URL 없음, URL 유출 시에도 의미 없음
}
```

**보안 보장**:
- ✅ OBS URL은 절대 반환되지 않음
- ✅ CDN URL(토큰 포함)도 절대 반환되지 않음
- ✅ 항상 `/photos/{id}/image` 같은 상대 경로만 반환
- ✅ 실제 이미지 접근 시에만 JWT로 권한 확인 후 CDN Auth Token 생성

### 2. 이미지 접근 흐름

```
1. 클라이언트: GET /photos/123/image + Authorization: Bearer JWT
2. 서버: JWT 검증 + 사진 소유자 확인
3. 서버: CDN Auth Token 생성 (유효기간 120초)
4. 서버: 302 Redirect → https://cdn.example.com/path?token=xxx
5. 클라이언트: CDN에서 이미지 다운로드 (토큰 검증됨)
```

### 3. 보안 보장 메커니즘

#### ✅ OBS는 public이지만 직접 접근 불가

- OBS URL을 직접 알더라도 CDN Auth Token 없이는 접근 불가
- CDN이 토큰을 검증하므로, 토큰이 없거나 만료된 요청은 거부됨

#### ✅ CDN Auth Token의 특징

1. **짧은 유효기간**: 기본 120초 (설정 가능)
2. **경로별 토큰**: 각 이미지 경로마다 고유한 토큰 생성
3. **자동 만료**: 토큰이 만료되면 CDN이 자동으로 거부

#### ✅ 권한 확인

- **일반 사용자**: JWT로 사진 소유자 확인 후 토큰 발급
- **공유 링크**: 공유 링크 유효성 확인 후 토큰 발급

## 설정 방법

### 환경 변수

```bash
# CDN 도메인
NHN_CDN_DOMAIN="https://your-cdn-domain.toastcdn.net"

# CDN App Key
NHN_CDN_APP_KEY="your-cdn-app-key"

# CDN Secret Key (API 인증용)
NHN_CDN_SECRET_KEY="your-cdn-secret-key"

# CDN Token Encryption Key (토큰 생성용)
NHN_CDN_ENCRYPT_KEY="your-cdn-encrypt-key"

# 이미지 토큰 유효 시간 (초, 기본 120)
IMAGE_TOKEN_EXPIRE_SECONDS=120
```

### CDN 콘솔 설정

1. **CDN 도메인 설정**: NHN Cloud 콘솔에서 CDN 도메인 생성
2. **원본 설정**: Object Storage를 원본으로 설정 (public으로 설정)
3. **인증 토큰 설정**: CDN 콘솔에서 인증 토큰 활성화 및 Encryption Key 설정

## 보안 검증

### ✅ 시나리오 1: 일반 이미지 - 링크만으로 접근 시도 (차단됨)

```
사용자가 이미지 URL을 알고 있음:
https://api.example.com/photos/123/image

→ JWT 없이 접근 시도
→ API가 401 Unauthorized 반환
→ 접근 불가 ✅

→ JWT 있지만 소유자가 아님
→ API가 404 Not Found 반환
→ 접근 불가 ✅
```

### ✅ 시나리오 2: OBS URL 직접 접근 시도 (차단됨)

```
사용자가 OBS URL을 알고 있음:
https://object-storage.example.com/container/photo/photo/image/1/abc.jpg

→ OBS가 public이면 직접 접근 가능 (보안 문제!)
→ 하지만 API는 OBS URL을 절대 반환하지 않음
→ 사용자는 OBS URL을 알 수 없음
→ 만약 OBS URL을 알더라도, CDN Auth Token이 없으므로 CDN이 거부
→ 403 Forbidden 또는 401 Unauthorized
```

**중요**: 
- API 응답에서 OBS URL이 반환되지 않으므로, 사용자는 OBS URL을 알 수 없습니다.
- 일반 이미지는 **링크만으로 절대 접근할 수 없습니다**. JWT와 소유자 확인이 필수입니다.

### ✅ 시나리오 3: 공유 링크 이미지 (허용됨)

```
공유 링크 토큰으로 접근:
https://api.example.com/share/{token}/photos/123/image

→ 공유 링크 토큰 유효성 확인
→ 해당 앨범에 포함된 사진인지 확인
→ CDN Auth Token 생성 후 302 리다이렉트
→ 접근 허용 ✅
```

### ✅ 시나리오 2: 만료된 토큰 사용 시도

```
사용자가 이전에 받은 CDN URL을 저장:
https://cdn.example.com/path?token=expired_token

→ 토큰이 만료되었으므로 CDN이 거부
→ 403 Forbidden
```

### ✅ 시나리오 3: 정상적인 접근

```
1. 사용자가 JWT로 /photos/123/image 요청
2. 서버가 권한 확인 후 CDN Auth Token 생성
3. 302 Redirect로 CDN URL 반환
4. 브라우저가 CDN에서 이미지 다운로드
5. CDN이 토큰 검증 후 이미지 제공
```

## 공유 링크 사용자

공유 링크 사용자의 경우도 동일한 방식으로 보안이 보장됩니다:

1. 공유 링크 토큰으로 앨범 접근 권한 확인
2. CDN Auth Token 생성 (일반 사용자와 동일)
3. 302 Redirect로 CDN URL 반환

**중요**: 공유 링크 사용자가 아닌 경우, 공유 링크 토큰 없이는 이미지에 접근할 수 없습니다.

## 성능 이점

- **CDN 캐싱**: 첫 요청 후 CDN이 이미지를 캐시하여 빠른 응답
- **백엔드 부하 감소**: 이미지 트래픽이 백엔드를 거치지 않음
- **전역 분산**: CDN 엣지 서버에서 전 세계 어디서나 빠른 접근

## 정리

| 항목 | 일반 이미지 | 공유 링크 이미지 |
|------|-----------|----------------|
| **접근 방법** | `/photos/{id}/image` + JWT | `/share/{token}/photos/{id}/image` |
| **인증 필요** | ✅ JWT 필수 | ❌ 공유 링크 토큰만 필요 |
| **소유자 확인** | ✅ 필수 | ❌ 앨범 소속 확인만 |
| **링크만으로 접근** | ❌ 불가능 | ✅ 가능 (공유 링크 토큰 필요) |
| **OBS URL 직접 접근** | ❌ 불가능 (토큰 없음) | ❌ 불가능 (토큰 없음) |
| **CDN Auth Token** | ✅ 사용 (JWT 확인 후) | ✅ 사용 (공유 링크 확인 후) |
| **토큰 유효기간** | 120초 (설정 가능) | 120초 (설정 가능) |
| **보안** | ✅ 보장됨 | ✅ 보장됨 (공유 링크로만 접근) |

### 보안 보장 메커니즘

1. **일반 이미지**: 
   - JWT 없이 접근 불가 (401 Unauthorized)
   - 소유자가 아니면 접근 불가 (404 Not Found)
   - OBS URL을 절대 반환하지 않음
   - CDN Auth Token이 없으면 CDN이 접근 거부

2. **공유 링크 이미지**:
   - 공유 링크 토큰으로만 접근 가능
   - 해당 앨범에 포함된 사진만 접근 가능
   - OBS URL을 절대 반환하지 않음
   - CDN Auth Token이 없으면 CDN이 접근 거부

3. **OBS 설정**:
   - Public (CDN 사용을 위해 필수)
   - 하지만 OBS URL을 직접 알 수 없음
   - CDN Auth Token 없이는 접근 불가

## 참고 문서

- [NHN Cloud CDN Auth Token API](https://docs.nhncloud.com/ko/Contents%20Delivery/CDN/ko/api-guide-v2.0/#auth-token-api)
- [IMAGE_ACCESS.md](./IMAGE_ACCESS.md) - 이미지 접근 방식 상세 설명
- [PRESIGNED_URL_GUIDE.md](./PRESIGNED_URL_GUIDE.md) - 업로드/다운로드 가이드
