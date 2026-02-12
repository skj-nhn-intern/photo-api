# NHN Cloud Object Storage Presigned URL 사용 가이드

이 문서는 NHN Cloud Object Storage의 S3 호환 API를 사용하여 presigned URL 방식으로 이미지를 업로드하는 방법을 설명합니다.

## 참조 문서

- [NHN Cloud Object Storage S3 API 가이드](https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/s3-api-guide/)

## Presigned URL 방식의 장점

1. **서버 부하 감소**: 파일이 서버를 거치지 않고 클라이언트에서 Object Storage로 직접 업로드됩니다.
2. **업로드 속도 향상**: 중간 경유 없이 직접 업로드하므로 속도가 빠릅니다.
3. **서버 대역폭 절약**: 서버의 네트워크 트래픽이 크게 줄어듭니다.
4. **확장성**: 서버 없이도 대용량 파일 업로드를 처리할 수 있습니다.

## 설정

### 1. S3 API 자격 증명 발급

NHN Cloud 콘솔에서 S3 API 자격 증명을 발급받습니다:

1. NHN Cloud Console 로그인
2. **Storage > Object Storage** 메뉴로 이동
3. **API 엔드포인트 설정** 탭에서 **S3 API 자격 증명** 발급
4. Access Key와 Secret Key를 안전하게 보관

참조: https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/s3-api-guide/#s3-api-s3-api-credential

### 2. 환경 변수 설정

발급받은 자격 증명을 환경 변수로 설정합니다:

```bash
# S3 API Credentials (Presigned URL 사용)
export NHN_S3_ACCESS_KEY="your_access_key"
export NHN_S3_SECRET_KEY="your_secret_key"
export NHN_S3_ENDPOINT_URL="https://kr1-api-object-storage.nhncloudservice.com"
export NHN_S3_REGION_NAME="kr1"
export NHN_S3_PRESIGNED_URL_EXPIRE_SECONDS="3600"  # 1시간 (기본값)
```

## API 사용 방법

### 워크플로우

Presigned URL을 사용한 업로드는 3단계로 구성됩니다:

```
1. Presigned URL 발급 (POST /photos/presigned-url)
   ↓
2. Object Storage에 직접 업로드 (PUT {presigned_url})
   ↓
3. 업로드 완료 확인 (POST /photos/confirm)
```

### 1. Presigned URL 발급

**Endpoint:** `POST /photos/presigned-url`

**Request:**
```json
{
  "album_id": 1,
  "filename": "my-photo.jpg",
  "content_type": "image/jpeg",
  "file_size": 1024000,
  "title": "제목 (선택)",
  "description": "설명 (선택)"
}
```

**Response:**
```json
{
  "photo_id": 123,
  "upload_url": "https://kr1-api-object-storage.nhncloudservice.com/v1/AUTH_xxx/photo-container/image/1/abc123.jpg?...",
  "object_key": "image/1/abc123.jpg",
  "expires_in": 3600,
  "upload_method": "PUT"
}
```

### 2. Object Storage에 직접 업로드

발급받은 `upload_url`로 PUT 요청을 보내 파일을 업로드합니다.

**중요:** 
- HTTP 메서드는 반드시 `PUT`을 사용해야 합니다.
- `Content-Type` 헤더는 1단계에서 지정한 값과 동일해야 합니다.

**예시 (cURL):**
```bash
curl -X PUT \
  -H "Content-Type: image/jpeg" \
  --data-binary "@my-photo.jpg" \
  "https://kr1-api-object-storage.nhncloudservice.com/..."
```

### 3. 업로드 완료 확인

**Endpoint:** `POST /photos/confirm`

**Request:**
```json
{
  "photo_id": 123
}
```

**Response:**
```json
{
  "photo_id": 123,
  "filename": "my-photo.jpg",
  "url": "https://xxx.toastcdn.net/photo-container/image/1/abc123.jpg?...",
  "message": "Photo upload confirmed successfully"
}
```

## 클라이언트 구현 예시

### JavaScript (Fetch API)

```javascript
async function uploadPhotoWithPresignedUrl(file, albumId) {
  try {
    // 1. Presigned URL 발급
    const presignedResponse = await fetch('/photos/presigned-url', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer YOUR_JWT_TOKEN'
      },
      body: JSON.stringify({
        album_id: albumId,
        filename: file.name,
        content_type: file.type,
        file_size: file.size,
        title: '내 사진',
        description: '설명'
      })
    });
    
    if (!presignedResponse.ok) {
      throw new Error('Presigned URL 발급 실패');
    }
    
    const presignedData = await presignedResponse.json();
    console.log('Presigned URL 발급 완료:', presignedData);
    
    // 2. Object Storage에 직접 업로드
    const uploadResponse = await fetch(presignedData.upload_url, {
      method: 'PUT',
      headers: {
        'Content-Type': file.type
      },
      body: file
    });
    
    if (!uploadResponse.ok) {
      throw new Error('파일 업로드 실패');
    }
    
    console.log('파일 업로드 완료');
    
    // 3. 업로드 완료 확인
    const confirmResponse = await fetch('/photos/confirm', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer YOUR_JWT_TOKEN'
      },
      body: JSON.stringify({
        photo_id: presignedData.photo_id
      })
    });
    
    if (!confirmResponse.ok) {
      throw new Error('업로드 확인 실패');
    }
    
    const confirmData = await confirmResponse.json();
    console.log('업로드 확인 완료:', confirmData);
    
    return confirmData;
    
  } catch (error) {
    console.error('업로드 오류:', error);
    throw error;
  }
}

// 사용 예시
const fileInput = document.querySelector('#file-input');
const file = fileInput.files[0];
const result = await uploadPhotoWithPresignedUrl(file, 1);
console.log('최종 결과:', result);
```

### Python (requests)

```python
import requests

def upload_photo_with_presigned_url(file_path: str, album_id: int, jwt_token: str):
    """Presigned URL을 사용하여 사진 업로드"""
    
    # 파일 정보 읽기
    import os
    import mimetypes
    
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    content_type = mimetypes.guess_type(file_path)[0] or 'image/jpeg'
    
    # 1. Presigned URL 발급
    presigned_response = requests.post(
        'http://localhost:8000/photos/presigned-url',
        headers={
            'Authorization': f'Bearer {jwt_token}',
            'Content-Type': 'application/json'
        },
        json={
            'album_id': album_id,
            'filename': filename,
            'content_type': content_type,
            'file_size': file_size
        }
    )
    presigned_response.raise_for_status()
    presigned_data = presigned_response.json()
    print(f"Presigned URL 발급 완료: {presigned_data['photo_id']}")
    
    # 2. Object Storage에 직접 업로드
    with open(file_path, 'rb') as f:
        upload_response = requests.put(
            presigned_data['upload_url'],
            headers={'Content-Type': content_type},
            data=f
        )
    upload_response.raise_for_status()
    print("파일 업로드 완료")
    
    # 3. 업로드 완료 확인
    confirm_response = requests.post(
        'http://localhost:8000/photos/confirm',
        headers={
            'Authorization': f'Bearer {jwt_token}',
            'Content-Type': 'application/json'
        },
        json={'photo_id': presigned_data['photo_id']}
    )
    confirm_response.raise_for_status()
    confirm_data = confirm_response.json()
    print(f"업로드 확인 완료: {confirm_data}")
    
    return confirm_data

# 사용 예시
result = upload_photo_with_presigned_url(
    file_path='my-photo.jpg',
    album_id=1,
    jwt_token='your_jwt_token'
)
```

### React + Axios

```javascript
import axios from 'axios';

const uploadPhotoWithPresignedUrl = async (file, albumId, jwtToken) => {
  try {
    // 1. Presigned URL 발급
    const { data: presignedData } = await axios.post(
      '/photos/presigned-url',
      {
        album_id: albumId,
        filename: file.name,
        content_type: file.type,
        file_size: file.size,
      },
      {
        headers: { Authorization: `Bearer ${jwtToken}` }
      }
    );
    
    console.log('Presigned URL 발급:', presignedData);
    
    // 2. Object Storage에 직접 업로드
    await axios.put(presignedData.upload_url, file, {
      headers: { 'Content-Type': file.type }
    });
    
    console.log('파일 업로드 완료');
    
    // 3. 업로드 완료 확인
    const { data: confirmData } = await axios.post(
      '/photos/confirm',
      { photo_id: presignedData.photo_id },
      {
        headers: { Authorization: `Bearer ${jwtToken}` }
      }
    );
    
    console.log('업로드 확인:', confirmData);
    return confirmData;
    
  } catch (error) {
    console.error('업로드 오류:', error);
    throw error;
  }
};

// React 컴포넌트에서 사용
function PhotoUploader({ albumId, jwtToken }) {
  const handleFileChange = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    
    try {
      const result = await uploadPhotoWithPresignedUrl(file, albumId, jwtToken);
      alert('업로드 성공!');
      console.log('업로드된 사진 URL:', result.url);
    } catch (error) {
      alert('업로드 실패: ' + error.message);
    }
  };
  
  return (
    <input type="file" accept="image/*" onChange={handleFileChange} />
  );
}
```

## 에러 처리

### 일반적인 에러와 해결 방법

| 에러 | 원인 | 해결 방법 |
|------|------|----------|
| `403 Forbidden` (단계 2) | S3 자격 증명이 올바르지 않음 | `NHN_S3_ACCESS_KEY`와 `NHN_S3_SECRET_KEY` 확인 |
| `403 Forbidden` (단계 2) | Presigned URL이 만료됨 | `NHN_S3_PRESIGNED_URL_EXPIRE_SECONDS` 값을 늘리거나 빠르게 업로드 |
| `400 Bad Request` (단계 3) | 파일이 실제로 업로드되지 않음 | 단계 2의 업로드가 성공했는지 확인 (HTTP 200 응답) |
| `413 Request Entity Too Large` | 파일 크기가 너무 큼 | 최대 10MB 이하로 제한 |
| `400 Bad Request` | 지원하지 않는 파일 형식 | JPEG, PNG, GIF, WebP, HEIC만 지원 |

### 에러 처리 예시

```javascript
async function uploadWithErrorHandling(file, albumId, jwtToken) {
  try {
    // 파일 크기 확인
    if (file.size > 10 * 1024 * 1024) {
      throw new Error('파일 크기는 10MB를 초과할 수 없습니다.');
    }
    
    // 파일 형식 확인
    const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/heic'];
    if (!allowedTypes.includes(file.type)) {
      throw new Error('지원하지 않는 파일 형식입니다.');
    }
    
    const result = await uploadPhotoWithPresignedUrl(file, albumId, jwtToken);
    return result;
    
  } catch (error) {
    if (error.response) {
      // 서버에서 반환한 에러
      const status = error.response.status;
      const detail = error.response.data?.detail;
      
      if (status === 403) {
        console.error('권한 오류:', detail);
        throw new Error('업로드 권한이 없습니다.');
      } else if (status === 404) {
        console.error('앨범을 찾을 수 없음:', detail);
        throw new Error('앨범을 찾을 수 없습니다.');
      } else if (status === 413) {
        console.error('파일 크기 초과:', detail);
        throw new Error('파일 크기가 너무 큽니다.');
      } else {
        console.error('서버 오류:', detail);
        throw new Error('업로드 중 오류가 발생했습니다.');
      }
    } else {
      // 네트워크 오류 등
      console.error('클라이언트 오류:', error);
      throw error;
    }
  }
}
```

## 보안 고려사항

1. **Presigned URL 노출 주의**: Presigned URL은 만료 시간 내에는 누구나 사용할 수 있으므로 노출에 주의하세요.
2. **만료 시간 설정**: 필요한 최소한의 시간으로 설정하세요 (기본 1시간).
3. **HTTPS 사용**: 반드시 HTTPS를 사용하여 통신하세요.
4. **JWT 토큰 보안**: API 호출 시 사용하는 JWT 토큰을 안전하게 관리하세요.

## 성능 최적화

1. **병렬 업로드**: 여러 파일을 동시에 업로드할 경우 Promise.all을 사용하세요.
2. **진행률 표시**: XMLHttpRequest나 axios를 사용하여 업로드 진행률을 표시할 수 있습니다.
3. **재시도 로직**: 네트워크 오류 시 자동 재시도 로직을 구현하세요.

### 진행률 표시 예시 (Axios)

```javascript
async function uploadWithProgress(file, albumId, jwtToken, onProgress) {
  // 1. Presigned URL 발급
  const { data: presignedData } = await axios.post(
    '/photos/presigned-url',
    {
      album_id: albumId,
      filename: file.name,
      content_type: file.type,
      file_size: file.size,
    },
    {
      headers: { Authorization: `Bearer ${jwtToken}` }
    }
  );
  
  // 2. 진행률과 함께 업로드
  await axios.put(presignedData.upload_url, file, {
    headers: { 'Content-Type': file.type },
    onUploadProgress: (progressEvent) => {
      const percentCompleted = Math.round(
        (progressEvent.loaded * 100) / progressEvent.total
      );
      onProgress(percentCompleted);
    }
  });
  
  // 3. 업로드 완료 확인
  const { data: confirmData } = await axios.post(
    '/photos/confirm',
    { photo_id: presignedData.photo_id },
    {
      headers: { Authorization: `Bearer ${jwtToken}` }
    }
  );
  
  return confirmData;
}

// 사용 예시
uploadWithProgress(file, 1, jwtToken, (percent) => {
  console.log(`업로드 진행률: ${percent}%`);
});
```

## 레거시 직접 업로드와의 비교

### 레거시 방식 (POST /photos/)
```
클라이언트 → [파일] → 서버 → [파일] → Object Storage
```
- 서버가 파일을 중계
- 서버 부하 높음
- 업로드 속도 상대적으로 느림

### Presigned URL 방식 (권장)
```
클라이언트 → [메타데이터] → 서버 → [Presigned URL] → 클라이언트
클라이언트 → [파일] → Object Storage (직접)
```
- 서버는 메타데이터만 처리
- 서버 부하 낮음
- 업로드 속도 빠름

## 문제 해결

### Presigned URL 접속 실패 (400 Bad Request on OPTIONS)

브라우저에서 프론트엔드(예: `https://myapp.com`)가 Object Storage 도메인(`https://kr1-api-object-storage.nhncloudservice.com`)으로 **cross-origin** 요청을 보낼 때, 브라우저는 먼저 **CORS preflight**로 `OPTIONS` 요청을 보냅니다. Object Storage 버킷에 CORS가 설정되어 있지 않으면 `OPTIONS`에 대해 **400 Bad Request**가 반환되어 presigned URL 접속이 실패합니다.

**해결 방법: Object Storage 버킷에 CORS 설정**

1. **NHN Cloud Console** → **Storage** → **Object Storage** → 해당 컨테이너(버킷) 선택  
2. **CORS 설정** 또는 **API 엔드포인트 설정** 메뉴에서 CORS 정책 추가  
3. 아래와 같이 설정합니다 (프로덕션에서는 `AllowedOrigin`을 실제 프론트엔드 도메인으로 제한하는 것을 권장합니다).

**CORS 정책 예시 (S3 호환 API 사용 시):**

- **AllowedOrigin**: `*` (개발용) 또는 `https://your-frontend-domain.com`
- **AllowedMethod**: `GET`, `PUT`, `HEAD`, `OPTIONS`
- **AllowedHeader**: `*` 또는 `Content-Type`, `Authorization`, `x-amz-*` 등 필요한 헤더
- **ExposeHeader**: (필요 시) `ETag`
- **MaxAgeSeconds**: `3600`

API로 설정할 경우: [PutBucketCORS](https://api-gov.ncloud-docs.com/docs/storage-objectstorage-putbucketcors) 문서를 참고하여 `{bucket-name}?cors=` 엔드포인트에 PUT 요청으로 XML CORS 정책을 적용합니다.

**요약:** Presigned URL은 서버에서 정상 생성되지만, **브라우저가 다른 오리진으로 요청할 때** 반드시 **버킷 CORS**가 허용되어 있어야 합니다. 400이 OPTIONS 요청에서 난다면 CORS 미설정이 원인입니다.

### InvalidBucketName (BucketName: v1)

에러 예: `<Code>InvalidBucketName</Code><Message>The specified bucket is not valid.</Message><BucketName>v1</BucketName>`

**원인:** S3 API 엔드포인트 URL에 **경로**(`/v1/AUTH_xxx` 등)가 포함되어 있으면, 생성된 presigned URL이 `.../v1/AUTH_xxx/컨테이너/...` 형태가 되고, 스토리지가 **첫 경로 세그먼트 `v1`을 버킷 이름**으로 잘못 해석합니다.

**해결:** `NHN_S3_ENDPOINT_URL` 은 **호스트만** 설정하세요. 경로를 넣지 마세요.

- 잘못된 예: `https://kr1-api-object-storage.nhncloudservice.com/v1/AUTH_5883ff5244d6421e964eb56f20f93e76`
- 올바른 예: `https://kr1-api-object-storage.nhncloudservice.com`

애플리케이션에서는 엔드포인트에서 경로를 제거한 뒤 S3 클라이언트를 생성하므로, 기존에 경로를 넣었더라도 동작은 보정됩니다. 새로 설정할 때는 위와 같이 호스트만 넣는 것을 권장합니다.

### SignatureDoesNotMatch (서명 불일치)

에러 예: `<Code>SignatureDoesNotMatch</Code><Message>The request signature we calculated does not match the signature you provided.</Message>`

**원인:** presigned URL 생성 시 사용한 정보와 실제 PUT 요청이 **조금이라도 다르면** 서명이 맞지 않습니다.

**체크리스트:**

1. **Content-Type을 반드시 맞추기**  
   presigned URL을 발급받을 때 넣은 `content_type`(예: `image/png`)과 **실제 PUT 요청의 `Content-Type` 헤더가 동일**해야 합니다.  
   - API 응답의 `upload_headers.Content-Type` 값을 그대로 사용하세요.  
   - 다른 값을 보내거나, 헤더를 빼면 서명 불일치가 납니다.

2. **헤더는 필요한 것만**  
   PUT 시 **`Content-Type`만 추가**하고, 서명에 포함되지 않은 커스텀 헤더를 붙이지 마세요.  
   (Host는 브라우저가 자동으로 넣습니다.)

3. **S3 API 전용 자격 증명 사용**  
   `NHN_S3_ACCESS_KEY` / `NHN_S3_SECRET_KEY`는 콘솔에서 발급한 **S3 API(EC2 형식) 자격 증명**이어야 합니다.  
   Swift/IAM 사용자 비밀번호와 혼동하지 마세요.  
   - 시크릿 키 앞뒤 공백, 줄바꿈이 없어야 합니다.

4. **Presigned URL 그대로 사용**  
   받은 URL을 수정하거나 쿼리 파라미를 추가/제거하면 서명이 깨집니다.  
   그대로 한 번에 PUT에 사용하세요.

5. **시간 동기화**  
   서버(또는 presigned URL을 생성한 환경)와 NHN Cloud 서버의 시각이 크게 어긋나면 서명 오류가 날 수 있습니다.  
   NTP 등으로 시간을 맞춰 두세요.

**클라이언트 예시 (fetch):**

```javascript
// 1) presigned-url 응답에서 받은 값 사용
const { upload_url, upload_headers } = await presignedResponse.json();
await fetch(upload_url, {
  method: 'PUT',
  headers: {
    'Content-Type': upload_headers['Content-Type']   // 반드시 동일
  },
  body: file
});
```

---

### 테스트 방법

```bash
# 1. Presigned URL 발급 테스트
curl -X POST http://localhost:8000/photos/presigned-url \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "album_id": 1,
    "filename": "test.jpg",
    "content_type": "image/jpeg",
    "file_size": 1024000
  }'

# 2. 업로드 테스트 (위에서 받은 upload_url 사용)
curl -X PUT "PRESIGNED_URL_HERE" \
  -H "Content-Type: image/jpeg" \
  --data-binary "@test.jpg"

# 3. 업로드 확인 테스트
curl -X POST http://localhost:8000/photos/confirm \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "photo_id": 123
  }'
```

### 로그 확인

서버 로그에서 다음 이벤트를 확인할 수 있습니다:

```
INFO: Presigned URL generated (photo_id=123, user_id=1)
INFO: Photo upload confirmed (photo_id=123, user_id=1)
```

에러 발생 시:
```
ERROR: Presigned URL generation failed
ERROR: Photo upload verification failed - file not found
```

## 추가 리소스

- [NHN Cloud Object Storage 문서](https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/overview/)
- [S3 API 가이드](https://docs.nhncloud.com/ko/Storage/Object%20Storage/ko/s3-api-guide/)
- [AWS SDK for Python (Boto3)](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
- [Presigned URLs (AWS 문서)](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html)
