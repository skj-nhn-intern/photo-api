# NHN Cloud Deploy 자동 배포 가이드

## 개요

GitHub Actions를 통해 dev 브랜치에 `v0.0.1` 태그가 푸시되면 자동으로 NHN Cloud Deploy Binary에 업로드됩니다.

## 설정 방법

### 1. GitHub Secrets 설정

GitHub 저장소의 Settings → Secrets and variables → Actions에서 다음 Secrets를 추가하세요:

- `NHN_CLOUD_APP_KEY`: NHN Cloud Deploy 프로젝트의 App Key
- `NHN_CLOUD_ARTIFACT_ID`: Artifact ID
- `NHN_CLOUD_BINARY_GROUP_ID_DEV`: dev-api-server Binary Group ID
- `NHN_CLOUD_BINARY_GROUP_ID_RELEASE`: release-api-server Binary Group ID
- `NHN_CLOUD_AUTH_ID`: API 인증 ID (NHN Cloud Deploy 콘솔의 API 보안 설정에서 발급)
- `NHN_CLOUD_AUTH_SECRET`: API 인증 Secret (NHN Cloud Deploy 콘솔의 API 보안 설정에서 발급)

**NHN_CLOUD_AUTH_ID와 SECRET 발급 방법:**
1. NHN Cloud 콘솔 접속
2. Dev Tools → Deploy 서비스 선택
3. 프로젝트 선택
4. **API 보안 설정** 메뉴로 이동
5. **User Access Key ID**와 **Secret Access Key** 생성/확인
6. 생성된 값을 GitHub Secrets에 저장

### 2. Binary Group 생성

NHN Cloud 콘솔에서:
1. Deploy 서비스 → Binary Groups 메뉴로 이동
2. `dev-api-server` Binary Group 생성 (개발 환경용)
3. `release-api-server` Binary Group 생성 (릴리스 환경용)
4. 각 Binary Group ID를 복사하여 GitHub Secret에 설정

### 3. 배포 트리거

#### dev 브랜치 배포
dev 브랜치에 태그를 푸시하거나 직접 푸시하면 `dev-api-server` Binary Group에 업로드됩니다:

```bash
# dev 브랜치로 체크아웃
git checkout dev

# 태그 생성 및 푸시 (예: v1.2.3)
git tag v1.2.3
git push origin v1.2.3
```

또는 dev 브랜치에 직접 푸시:

```bash
git checkout dev
git merge main  # 또는 다른 브랜치
git push origin dev
```

#### release 브랜치 배포
release 브랜치로 머지하면 해당 버전으로 `release-api-server` Binary Group에 업로드됩니다:

```bash
# release 브랜치로 체크아웃
git checkout release

# dev 브랜치 머지 (버전 태그가 포함되어 있어야 함)
git merge dev
git push origin release
```

**주의**: release 브랜치로 머지할 때는 버전 태그가 있어야 합니다. 태그가 없으면 배포가 실패합니다.

## 배포 패키지 구성

배포 패키지에는 다음 파일들이 포함됩니다:

- `app/`: 애플리케이션 소스 코드
- `requirements.txt`: Python 의존성
- `setup.sh`: 설치 스크립트
- `entrypoint.sh`: 실행 스크립트
- `README.md`: 문서

## 배포 후 설치

NHN Cloud Deploy를 통해 배포된 바이너리를 서버에 설치하려면:

```bash
# 압축 파일 다운로드 및 압축 해제
tar -xzf photo-api-v0.0.1.tar.gz
cd photo-api-v0.0.1

# 설치 스크립트 실행
sudo ./setup.sh
```

## 참고

- NHN Cloud Deploy API 문서: https://docs.nhncloud.com/ko/Dev%20Tools/Deploy/ko/api-guide-v1.0/
- Binary 업로드 API: https://api-tcd.nhncloudservice.com/api/v1.0/projects/{appKey}/artifacts/{artifactId}/binary-groups/{binaryGroupId}/binaries
