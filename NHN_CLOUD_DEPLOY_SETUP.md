# NHN Cloud Deploy API 인증 정보 설정 가이드

## NHN_CLOUD_AUTH_ID와 SECRET이란?

NHN Cloud Deploy API를 사용하기 위한 인증 정보입니다. **IAM과는 별개**이며, Deploy 서비스 자체의 API 보안 설정에서 발급받습니다.

- **NHN_CLOUD_AUTH_ID**: User Access Key ID (Deploy API 보안 설정에서 발급)
- **NHN_CLOUD_AUTH_SECRET**: Secret Access Key (Deploy API 보안 설정에서 발급)

⚠️ **주의**: 이것은 **IAM 인증 정보가 아닙니다**. NHN Cloud Deploy 서비스의 API 보안 설정에서 별도로 발급받는 인증 정보입니다.

## 발급 방법

NHN Cloud Deploy API 문서([링크](https://docs.nhncloud.com/ko/Dev%20Tools/Deploy/ko/api-guide-v1.0/))에 따르면, API 호출 시 다음 헤더가 필요합니다:

- `X-TC-AUTHENTICATION-ID`: API 보안 설정 메뉴의 User Access Key ID
- `X-TC-AUTHENTICATION-SECRET`: API 보안 설정 메뉴의 Secret Access Key

### 1. NHN Cloud 콘솔 접속
1. NHN Cloud 콘솔에 로그인
2. **Dev Tools** → **Deploy** 서비스 선택

### 2. 프로젝트 선택
- Deploy 프로젝트 선택 (또는 새로 생성)

### 3. API 보안 설정 찾기 (IAM 아님!)

⚠️ **중요**: 이것은 **IAM이 아닙니다**. NHN Cloud Deploy 서비스의 **API 보안 설정**에서 발급받습니다.

NHN Cloud Deploy 콘솔에서:
1. 프로젝트 선택 후 프로젝트 설정 메뉴 확인
2. **API 보안 설정** 또는 **API 인증 설정** 메뉴 찾기
   - IAM 설정이 아닌 **Deploy API 보안 설정**입니다
3. 또는 프로젝트 상세 페이지에서 API 관련 설정 메뉴 확인

**참고**: 메뉴 위치는 NHN Cloud 콘솔 버전에 따라 다를 수 있습니다. 다음 위치를 확인해보세요:
- Deploy 프로젝트 설정 → API 보안
- Deploy 프로젝트 설정 → API 인증
- Deploy 프로젝트 상세 → API 설정

**IAM이 아닙니다!** Deploy 서비스 자체의 API 보안 설정입니다.

### 4. 인증 정보 확인/생성
1. **User Access Key ID** 확인 또는 생성
2. **Secret Access Key** 확인 또는 생성 (최초 생성 시에만 표시되므로 안전하게 보관)

### 4. GitHub Secrets에 저장
1. GitHub 저장소 → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** 클릭
3. 다음 Secrets 추가:
   - Name: `NHN_CLOUD_AUTH_ID`, Value: 발급받은 User Access Key ID
   - Name: `NHN_CLOUD_AUTH_SECRET`, Value: 발급받은 Secret Access Key

## 필요한 모든 Secrets 목록

GitHub Actions에서 사용하는 모든 Secrets:

1. **NHN_CLOUD_APP_KEY**: Deploy 프로젝트의 App Key
2. **NHN_CLOUD_ARTIFACT_ID**: Artifact ID
3. **NHN_CLOUD_BINARY_GROUP_ID_DEV**: dev-api-server Binary Group ID
4. **NHN_CLOUD_BINARY_GROUP_ID_RELEASE**: release-api-server Binary Group ID
5. **NHN_CLOUD_AUTH_ID**: API 인증 ID (User Access Key ID)
6. **NHN_CLOUD_AUTH_SECRET**: API 인증 Secret (Secret Access Key)

## API 사용 예시

이 인증 정보는 다음과 같이 API 호출에 사용됩니다:

```bash
curl -X POST \
  "https://api-tcd.nhncloudservice.com/api/v1.0/projects/${NHN_CLOUD_APP_KEY}/artifacts/${NHN_CLOUD_ARTIFACT_ID}/binary-groups/${BINARY_GROUP_ID}/binaries" \
  -H "X-TC-AUTHENTICATION-ID: ${NHN_CLOUD_AUTH_ID}" \
  -H "X-TC-AUTHENTICATION-SECRET: ${NHN_CLOUD_AUTH_SECRET}" \
  -F "file=@package.tar.gz" \
  -F "version=v1.0.0"
```

## 보안 주의사항

⚠️ **중요**: 
- Secret Access Key는 최초 생성 시에만 표시되므로 안전하게 보관하세요
- GitHub Secrets에 저장하여 코드에 노출되지 않도록 하세요
- Secret이 유출되면 즉시 재생성하세요

## API 문서 참고

[NHN Cloud Deploy API 가이드](https://docs.nhncloud.com/ko/Dev%20Tools/Deploy/ko/api-guide-v1.0/)에 따르면:

### 바이너리 업로드 API
- **URL**: `https://api-tcd.nhncloudservice.com/api/v1.0/projects/{appKey}/artifacts/{artifactId}/binary-groups/{binaryGroupId}/binaries`
- **Method**: POST
- **Required Headers**:
  - `X-TC-AUTHENTICATION-ID`: API 보안 설정 메뉴의 User Access Key ID
  - `X-TC-AUTHENTICATION-SECRET`: API 보안 설정 메뉴의 Secret Access Key
  - `Content-Type`: multipart/form-data

### 인증 정보 위치
문서에는 헤더 형식만 명시되어 있고, 실제 발급 방법은 **NHN Cloud 콘솔의 API 보안 설정 메뉴**에서 확인해야 합니다.

콘솔에서 찾을 수 없는 경우:
1. NHN Cloud 고객 지원팀에 문의
2. Deploy 서비스 사용 가이드 확인
3. 프로젝트 생성 시 자동 발급 여부 확인
