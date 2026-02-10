# NHN Deploy로 Photo API 배포

이미지 빌드는 GitHub Actions에서 하고, **실제 서버에 환경 변수 반영·서비스 재시작**은 NHN Deploy로 하는 구성을 안내합니다.

## 전제

- 서버에는 이미 **Photo API 인스턴스 이미지**로 생성된 인스턴스가 떠 있고, `/opt/photo-api`에 앱이 설치되어 있음.
- systemd 서비스명: `photo-api.service`, 환경 변수 파일: `/opt/photo-api/.env`.

## NHN Deploy에서 할 일

1. **환경 변수 설정**  
   Deploy 콘솔의 **시나리오/서버 그룹**에서 리전별 환경 변수 설정  
   (예: `DATABASE_URL`, `JWT_SECRET_KEY`, `LOKI_URL`, `NHN_OBJECT_STORAGE_*`, `NHN_CDN_*` 등)  
   **Loki 로그 전송**: 배포 시나리오/서버 그룹 환경 변수에 `LOKI_URL`(예: `http://loki서버:3100`)을 **반드시** 넣어 주세요. 비어 있으면 Promtail이 `unsupported protocol scheme ""` 를 로그에 남기고, 재시작 시 `.env`에 반영된 값으로 정상 동작합니다.
2. **배포 시 실행할 스크립트**  
   이 디렉터리의 `apply-env-and-restart.sh`를 **User Command** 태스크로 실행해,  
   위에서 설정한 값을 `/opt/photo-api/.env`에 쓰고 `photo-api.service`를 재시작.

## 시나리오 구성 예시

| 순서 | 태스크 유형 | 설명 |
|------|-------------|------|
| 1 | **User Command** | `deploy/apply-env-and-restart.sh` 실행. Deploy에서 설정한 환경 변수를 export 한 뒤 실행 (아래 사용법 참고) |
| 2 | **User Command** (선택) | `deploy/verify-after-deploy.sh` 실행. 배포 후 서비스·헬스·API 응답 검증 |

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
   → 현재 셸에 **export** 된 변수만 .env에 반영합니다. **이번에 넘기지 않은 변수는 기존 .env 값을 유지**하므로, 배포 시 일부 변수만 넘겨도 LOKI_URL 등은 지워지지 않습니다.

2. **.env 내용을 stdin으로 넘기는 경우**  
   - `apply-env-and-restart.sh --stdin`  
   → 표준입력 내용으로 `/opt/photo-api/.env` **전체를 덮어쓴 뒤** 재시작. (기존 .env는 대체됨)

3. **재시작만 하는 경우**  
   - `apply-env-and-restart.sh --restart-only`  
   → .env는 수정하지 않고 photo-api·promtail만 재시작.

## 배포 후 검증 (verify-after-deploy.sh)

배포 직후 서비스가 정상 기동했는지 확인하려면 `verify-after-deploy.sh`를 실행합니다.

- **같은 서버에서**: `sudo /opt/photo-api/deploy/verify-after-deploy.sh`
- **원격에서**: `BASE_URL=http://서버IP:8000 ./verify-after-deploy.sh`

검증 항목: systemd 서비스 active 여부, `GET /health` → 200 + `"healthy"`, `GET /` 응답, `GET /metrics` (선택).  
실패 시 exit code 1을 반환하므로 Deploy 시나리오에서 “검증 실패 시 배포 실패”로 이어지게 할 수 있습니다.

환경 변수: `SERVICE_NAME`(기본 `photo-api`), `BASE_URL`(기본 `http://127.0.0.1:8000`), `MAX_WAIT`(기본 30초), `CURL_TIMEOUT`(기본 10초).

## Loki에 로그가 안 보일 때

로그 경로: **앱** → `/var/log/photo-api/app.log`, `error.log` → **Promtail** → **Loki**. 아래 순서로 확인하세요.

### Promtail 서비스가 아예 안 뜰 때

1. **unit 파일이 서버에 반영됐는지**  
   예전에 "LOKI_URL 비어 있으면 기동 스킵"하는 unit이 있으면, 비어 있을 때 Promtail이 바로 exit 0 해서 서비스가 안 떠 있을 수 있습니다.  
   **조치**: 저장소의 `conf/promtail.service`(스킵 없음)를 서버에 복사한 뒤 재시작하세요.
   ```bash
   sudo cp /opt/photo-api/conf/promtail.service /etc/systemd/system/promtail.service
   sudo systemctl daemon-reload
   sudo systemctl restart promtail
   sudo systemctl status promtail
   ```
2. **바이너리·설정 존재 여부**  
   `test -x /opt/promtail/promtail && test -f /opt/promtail/promtail-config.yaml && echo OK`  
   없으면 이미지 빌드/설치 단계에서 Promtail 설치가 빠진 것입니다.

### 로그는 쓰이는데 Loki에만 안 보일 때

3. **LOKI_URL이 .env에 있는지**  
   `sudo grep LOKI_URL /opt/photo-api/.env`  
   비어 있거나 없으면 배포 시나리오에 `LOKI_URL=http://loki서버:3100` 넣고 배포(또는 `apply-env-and-restart.sh`) 실행.

4. **Promtail 기동 여부**  
   `sudo systemctl status promtail`  
   inactive면 `sudo systemctl start promtail`. `.env`를 수정했다면 `sudo systemctl restart promtail` 로 재시작해야 새 LOKI_URL을 읽습니다.

5. **앱이 로그 파일을 쓰는지**  
   `ls -la /var/log/photo-api/`  
   `app.log` 크기가 늘어나는지 확인. 권한 문제면 `sudo chown -R photo-api:photo-api /var/log/photo-api` 등으로 조정.

6. **배포 후에는 반드시 Promtail 재시작**  
   `apply-env-and-restart.sh`는 `.env` 반영 후 `promtail`도 재시작하므로, 배포 한 번이면 LOKI_URL이 적용됩니다.

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
