# NHN Deploy로 Photo API 배포

이미지 빌드는 GitHub Actions에서 하고, **실제 서버에 환경 변수 반영·서비스 재시작**은 NHN Deploy로 하는 구성을 안내합니다.

## 전제

- 서버에는 이미 **Photo API 인스턴스 이미지**로 생성된 인스턴스가 떠 있고, `/opt/photo-api`에 앱이 설치되어 있음.
- systemd 서비스명: `photo-api.service`, 환경 변수 파일: `/opt/photo-api/.env`.

## NHN Deploy에서 할 일

1. **환경 변수 설정**  
   Deploy 콘솔의 **시나리오/서버 그룹**에서 리전별 환경 변수 설정  
   (예: `DATABASE_URL`, `JWT_SECRET_KEY`, `NHN_OBJECT_STORAGE_*`, `NHN_CDN_*` 등)
2. **배포 시 실행할 스크립트**  
   이 디렉터리의 `apply-env-and-restart.sh`를 **User Command** 태스크로 실행해,  
   위에서 설정한 값을 `/opt/photo-api/.env`에 쓰고 `photo-api.service`를 재시작.

## 시나리오 구성 예시

| 순서 | 태스크 유형 | 설명 |
|------|-------------|------|
| 1 | **User Command** | `deploy/apply-env-and-restart.sh` 실행. Deploy에서 설정한 환경 변수를 export 한 뒤 실행 (아래 사용법 참고) |

- **Run As**: 서버에서 `photo-api` 서비스 제어 권한이 있는 계정(예: `root`).
- **Timeout**: 1~2분 정도.
- **Command**:  
  - 스크립트를 서버에 두는 경우:  
    `sudo /opt/photo-api/deploy/apply-env-and-restart.sh`  
  - 또는 Deploy가 배포 파일을 특정 경로에 풀어준다면 그 경로의 스크립트 실행.

## apply-env-and-restart.sh 사용법

스크립트는 다음 중 한 가지 방식으로 동작합니다.

1. **환경 변수를 export 한 뒤 실행 (권장)**  
   NHN Deploy가 User Command 실행 시 환경 변수를 주입하면, 그대로 export 되어 있으므로 인자 없이 실행하면 됨.  
   - `apply-env-and-restart.sh`  
   → 현재 셸에 **export** 된 변수 중 `DATABASE_URL`, `JWT_SECRET_KEY`, `NHN_*`, `LOKI_URL` 등 앱에서 쓰는 이름만 골라 `/opt/photo-api/.env`에 쓰고 서비스 재시작.

2. **.env 내용을 stdin으로 넘기는 경우**  
   - `apply-env-and-restart.sh --stdin`  
   → 표준입력 내용을 `/opt/photo-api/.env`로 저장 후 재시작.

## 리포지터리에 스크립트 두기

- `deploy/apply-env-and-restart.sh`를 저장소에 포함해 두고,
- NHN Deploy **배포 파일**을 이 리포지터리(또는 빌드 결과물)에서 가져오도록 하면,  
  배포 시 항상 같은 스크립트를 실행할 수 있습니다.
- 인스턴스 이미지 안에 `/opt/photo-api/deploy/`를 미리 넣어 두었다면, User Command는  
  `sudo /opt/photo-api/deploy/apply-env-and-restart.sh`  
  한 줄이면 됩니다.

## 참고

- [NHN Cloud Deploy 콘솔 가이드](https://docs.nhncloud.com/ko/Dev%20Tools/Deploy/ko/console-guide/)
- [NHN Cloud Deploy 기능 상세(시나리오/태스크)](https://docs.nhncloud.com/ko/Dev%20Tools/Deploy/ko/reference/)
- 프로젝트 루트의 [ENVIRONMENT_SETUP.md](../ENVIRONMENT_SETUP.md) — 앱에서 사용하는 환경 변수 목록.
