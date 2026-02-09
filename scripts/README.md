# Ubuntu 인스턴스 이미지 빌드 스크립트

Ubuntu VM에서 **photo-api** 인스턴스 이미지를 만들 때 순서대로 실행하는 스크립트입니다.

**CI 전용 스크립트**: GitHub Actions에서 NHN Cloud 인스턴스 생성·이미지 생성·정리를 하는 Python 스크립트는 [scripts/ci/](ci/README.md)에 있습니다.  
(Packer 등으로 이미지 스냅샷/AMI 생성 시 이 VM에서 아래를 실행한 뒤 스냅샷을 찍으면 됩니다.)

## 순서 (한 번에 실행)

```bash
sudo ./scripts/build-image.sh
```

## 단계별 실행

| 순서 | 스크립트 | 내용 |
|------|----------|------|
| 1 | `sudo ./scripts/1-install-python.sh` | Python 3.11 및 시스템 의존성 설치 |
| 2 | `sudo ./scripts/2-setup-photo-api.sh` | photo-api를 /opt/photo-api에 복사 후 systemd 서비스 등록 |
| 3 | `sudo ./scripts/3-setup-promtail.sh` | Promtail 설치, 설정: `/opt/promtail/promtail-config.yaml` |

메트릭은 앱의 `/metrics` 엔드포인트로 제공되며, Prometheus 서버에서 스크래핑합니다. (Telegraf/InfluxDB 미사용)

## 사전 조건

- Ubuntu 22.04 LTS (또는 호환 배포)
- 스크립트 실행 시 **프로젝트 루트**(`app/main.py`, `requirements.txt`, `conf/promtail-config.yaml`)가 현재 머신에 있어야 함  
  - 다른 경로에 있으면 `PHOTO_API_SOURCE`, `PROMTAIL_CONF_SOURCE` 등으로 지정

## 환경 변수 (선택)

| 변수 | 설명 |
|------|------|
| `PHOTO_API_SOURCE` | photo-api 소스 디렉터리 (기본: 스크립트 기준 상위 또는 /opt/photo-api) |
| `SERVICE_HOME` | 앱 설치 경로 (기본: /opt/photo-api) |
| `PROMTAIL_VERSION` | Promtail 버전 (기본: 3.6.4) |
| `LOKI_URL` | Promtail → Loki 주소 (예: http://loki:3100, 이미지/배포 환경에 맞게 설정) |

## 설치 결과

- **photo-api**: `/opt/photo-api`, systemd 서비스 `photo-api`, 포트 8000, **Prometheus 메트릭**: `http://인스턴스:8000/metrics`
- **Promtail**: `/opt/promtail/`, 설정 `/opt/promtail/promtail-config.yaml`

**인스턴스 이미지와 systemctl**  
이미지는 디스크 스냅샷이라 서비스는 **중지된 상태**로 들어갑니다. 빌드 시 `systemctl enable`만 해 두었기 때문에, 이 이미지에서 **인스턴스를 부팅하면** photo-api, promtail이 **자동으로 기동**됩니다.  
수동 기동이 필요하면 인스턴스 안에서 **실행 스크립트**를 사용하세요:

```bash
sudo photo-api-run
```

(실제 경로: `/opt/photo-api/scripts/run-services.sh` — photo-api, promtail 기동)

이미지 생성 후 앱 설정(DB, Object Storage 등)을 위해 `/etc/default/photo-api`에 환경변수를 설정합니다. 예시: `conf/photo-api.env.example` 참고.

배포 방법은 [deploy/README.md](../deploy/README.md)를 참고하세요.
