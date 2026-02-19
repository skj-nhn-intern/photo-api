# GitHub Actions 자동 배포 흐름 및 배포 시간 단축 방안

## 1. 자동 배포 흐름 요약

워크플로우 파일: `.github/workflows/build-and-test-image.yml`

**트리거**: `main` / `develop` 브랜치에 push 또는 PR 시 실행 (또는 `workflow_dispatch` 수동 실행)

---

## 2. 단계별 흐름 (Sequential)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Job: build-and-create-image (ubuntu-22.04, timeout 90분)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  1. Set KR1 / Checkout / Set up Python / Install pip deps                    │
│  2. Create temporary SSH key                                                │
│  3. Create build instance on NHN Cloud (KR1)  ← 인스턴스 부팅 대기 포함      │
│  4. Wait for SSH to be ready (최대 30×10초 = 5분)                            │
│  5. Prepare build environment (.env.build)                                   │
│  6. Upload source code (rsync) → 빌드 인스턴스 /tmp/photo-api/              │
│  7. Download dependencies offline (pip download, Promtail, node_exporter)   │
│  8. Upload offline packages → 빌드 인스턴스 /tmp/offline-packages/          │
│  9. Build image on instance (SSH로 원격 실행):                               │
│     - apt update/install (Python 3.11, build-essential 등)                  │
│     - /opt/photo-api 설정, venv, pip install (offline)                       │
│     - Promtail, node_exporter 설치, systemd 서비스 등록                      │
│  10. Start services + API health check (최대 30×10초)                        │
│  11. Prepare image (cloud-init clean, sync)                                 │
│  12. Stop instance                                                          │
│  13. Create instance image (NHN Cloud API)                                  │
│  14. Create test instance from image (KR1)                                  │
│  15. Wait for test instance services (sleep 60)                             │
│  16. Check server time sync                                                 │
│  17. Test image with curl (health, /, /metrics, 9100) (최대 30×10초)        │
│  18. Summary                                                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│  Job: cleanup-resources (always, needs build-and-create-image)               │
│  - Checkout / Set up Python / Install deps / Get token / Cleanup KR1         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 예상 소요 시간 (대략)

| 단계 | 예상 시간 | 비고 |
|------|-----------|------|
| Runner 준비 + SSH 키 + Create build instance | 2~5분 | 인스턴스 ACTIVE 대기 |
| Wait for SSH | 0~5분 | 보통 1~2분 |
| Upload source + Prepare env | 0.5~1분 | |
| Download dependencies offline | 1~3분 | pip download, curl Promtail/node_exporter |
| Upload offline packages | 0.5~2분 | 패키지 크기에 따라 |
| Build image on instance | 5~15분 | apt, Python, venv, Promtail, node_exporter |
| Start + health check | 1~5분 | |
| Stop + Create image | 2~10분 | NHN 이미지 생성 시간 |
| Create test instance + wait 60s | 2~4분 | |
| Test image with curl | 1~5분 | |
| Cleanup job | 1~2분 | |
| **총계** | **약 17~57분** | 리전/네트워크/캐시에 따라 변동 |

---

## 4. 배포 시간 단축 방안

### 4.1. 병렬화 (효과: 중간~높음)

- **오프라인 패키지 다운로드와 소스 업로드 병렬화**  
  - 현재: “Download dependencies offline” → “Upload offline packages” → “Upload source” 는 순차.  
  - 제안: Runner에서 “Download dependencies offline”과 “Upload source code”를 **동시에** 실행할 수 있도록 step을 나누거나, 한 step 안에서 `&`로 백그라운드 실행 후 `wait`로 동기화.  
  - 단, “Upload offline packages”는 다운로드가 끝난 뒤에만 가능하므로, “Download” 완료 후 “Upload source”와 “Upload offline packages”를 병렬로 보내면 소스 업로드 시간을 숨길 수 있음.

- **캐시 활용**  
  - `actions/cache`로 `offline-packages`(pip download 결과, Promtail zip, node_exporter tarball)를 캐시.  
  - `requirements.txt`와 `PROMTAIL_VERSION`, `NODE_EXPORTER_VERSION`을 캐시 키에 포함.  
  - 캐시 히트 시 “Download dependencies offline” 단계를 거의 생략 가능 → **1~3분 절약**.

### 4.2. SSH/헬스체크 대기 시간 단축 (효과: 낮음~중간)

- **Wait for SSH**: 현재 10초 간격, 최대 30회(5분).  
  - 간격을 5초로 줄이거나, 초반에는 5초·이후 10초처럼 단계적으로 조정하면 실패 시에만 시간이 길어지고, 성공 시에는 **수십 초 절약** 가능.
- **Start services and verify API**, **Test image with curl**:  
  - 마찬가지로 재시도 간격을 5초로 줄이면 평균 대기 시간 감소.

### 4.3. 빌드 인스턴스 내부 작업 단축 (효과: 높음)

- **기본 이미지 선 반영**  
  - NHN 기본 이미지에 Python 3.11, `build-essential`, `libffi-dev`, `libssl-dev` 등이 미리 설치된 커스텀 베이스 이미지를 쓰면, 인스턴스 내부에서 `apt update/install` 시간이 **수 분 단축**됨.
- **오프라인 패키지 캐시와 동일하게**  
  - Runner 캐시로 “오프라인 패키지”를 쓰면, 인스턴스에는 이미 올라간 패키지로만 설치하므로 네트워크 의존이 없고, 위 “Download dependencies offline” 시간도 줄어듦.

### 4.4. 테스트 인스턴스 대기 시간 (효과: 낮음)

- **Wait for test instance services**: 현재 `sleep 60` 고정.  
  - 대신 “헬스체크 성공할 때까지” 폴링(예: 5초 간격, 최대 90초)으로 바꾸면, 서비스가 빨리 뜨는 경우 **수십 초 절약**.

### 4.5. Job 분리 (선택)

- “Create build instance” ~ “Create instance image”까지를 한 job으로 두고, “Create test instance” + “Test image”를 별도 job으로 두면, 이미지 생성 후 테스트만 재실행하기 쉬움.  
  - 배포 시간 자체보다는 **재시도/디버깅** 시 이점이 큼.

### 4.6. 요약 우선순위

| 순위 | 방안 | 예상 절감 | 구현 난이도 |
|------|------|-----------|-------------|
| 1 | `actions/cache`로 offline-packages 캐시 | 1~3분 | 낮음 |
| 2 | Python 3.11 등 포함한 NHN 베이스 이미지 사용 | 3~8분 | 중간(이미지 빌드/관리) |
| 3 | “Download deps”와 “Upload source” 병렬화 | 0.5~1.5분 | 중간 |
| 4 | 테스트 인스턴스 대기를 sleep 60 → 헬스체크 폴링 | 0~50초 | 낮음 |
| 5 | SSH/API 재시도 간격 10초 → 5초 | 0~1분 | 낮음 |

---

## 5. 빌드 과정이 전부 필요한가? (단계별 필요성)

### 5.1. 꼭 필요한 것 (제거하면 이미지/배포가 깨짐)

| 단계 | 이유 |
|------|------|
| Checkout, Set Python, NHN CLI deps, SSH 키 | Runner에서 NHN API 호출·인스턴스 접속에 필수 |
| Create build instance | VM 이미지를 만들려면 그 VM을 먼저 만들어야 함 |
| Wait for SSH | 이후 rsync/ssh가 가능해야 함 |
| Prepare build env (.env.build) | 앱이 기동하려면 DB, JWT, Object Storage 등 설정 필요 |
| Upload source + (오프라인 또는 온라인) 의존성 | 인스턴스 안에 앱·의존성이 있어야 이미지에 포함됨 |
| Build on instance (Python, photo-api, systemd) | 이미지 내용물을 만드는 핵심 단계 |
| Start services + API 헬스체크 | **이미지 생성 전** 앱이 뜨는지 확인. 없으면 깨진 이미지가 만들어질 수 있음 |
| cloud-init clean | 이걸 해야 이 이미지로 띄운 새 VM에서 cloud-init이 다시 돌아가 SSH 키 등 주입됨 |
| Stop instance → Create instance image | NHN에서 “인스턴스 → 이미지” 생성 절차 |
| Cleanup (빌드/테스트 인스턴스, 키페어 등) | 리소스 누수 방지 |

정리하면, **“빌드 인스턴스 띄우기 → 설치 → 헬스체크 → 정리 후 이미지 생성”** 흐름 자체는 NHN VM 이미지를 쓰는 한 필요하고, 그 안의 대부분 단계도 필수에 가깝습니다.

### 5.2. 줄이거나 생략할 수 있는 것

| 단계 | 필요성 | 생략/간소화 시 영향 |
|------|--------|----------------------|
| **테스트 인스턴스** (이미지로 VM 한 번 더 띄워서 헬스/메트릭 검증) | 권장 | “빌드 VM”에서는 앱이 돌아가도, **이미지에서 부팅한 VM**에서는 안 뜰 수 있음(cloud-init, 권한 등). 생략하면 배포 후에야 문제를 발견할 수 있음. 시간은 약 3~5분 추가. |
| **Promtail / node_exporter** 이미지 내 설치 | 선택 | 앱 자체 기동에는 불필요. 로그(Loki)·메트릭 수집용. 이걸 이미지에서 빼고 나중에 별도 에이전트/사이드카로 넣으면 빌드 단계·이미지 크기 감소 가능. |
| **오프라인 패키지** (Runner에서 pip download 후 인스턴스로 업로드) | 선택 | 빌드 인스턴스에 아웃바운드 인터넷이 허용되면, 인스턴스 안에서 직접 `pip install -r requirements.txt` + Promtail/node_exporter 다운로드 가능. 그러면 “Download dependencies offline” + “Upload offline packages” 제거 가능. 대신 네트워크/외부 의존성 생김. |
| **Check server time sync** | 선택 | CDN Temp URL(서명 URL) 검증을 위해 중요할 수 있음. 시간 오차가 크면 401 발생. 운영에서 이미 NTP 등을 신뢰하면 warning 수준으로 두거나 생략 가능. |
| **Test image 단계의 상세 검증** (/, /metrics, 9100, jq 등) | 선택 | “헬스만 확인”으로 줄이면 테스트 단계는 짧아짐. /, /metrics, node_exporter까지 보는 건 스모크 테스트 강화용. |

### 5.3. 대안 구조 (빌드 시간·복잡도 vs 안전성)

- **현 구조 유지**  
  - 테스트 인스턴스 + Promtail/node_exporter + 오프라인 빌드까지 모두 유지  
  - 장점: 이미지 품질·운영 환경에 가까운 검증, 재현 가능한 빌드.  
  - 단점: 단계 많고 시간 길다.

- **최소 필수만**  
  - 테스트 인스턴스 생략, Promtail/node_exporter는 이미지에서 제외(또는 별도 배포), 오프라인 대신 인스턴스에서 직접 pip/curl.  
  - 장점: 단계와 시간 크게 감소.  
  - 단점: “이미지에서 부팅한 VM” 검증이 없고, 로그/메트릭은 다른 방식으로 맞춰야 함.

- **절충**  
  - 테스트 인스턴스는 유지(이미지 품질 검증), Promtail/node_exporter만 이미지에서 빼거나, 오프라인만 인스턴스 온라인 설치로 바꾸기.  
  - 배포 시간과 안전성·운영 요구사항 사이에서 타협할 때 선택.

### 5.4. 한 줄 요약

- **전부 “다 필수”는 아니다.**  
  - 꼭 필요한 건 “빌드 인스턴스 생성 → 소스·의존성 올리기 → 인스턴스에서 설치 → 헬스체크 → cloud-init 정리 → 중지 후 이미지 생성 + 리소스 정리”까지.  
- **테스트 인스턴스, Promtail/node_exporter, 오프라인 빌드, 시간 동기화/상세 curl 검증**은 운영 정책과 트레이드오프에 따라 **줄이거나 생략**할 수 있고, 그만큼 빌드 시간·복잡도를 줄일 수 있다.

---

## 6. 참고

- 실제 시간은 NHN Cloud API 응답 속도, 인스턴스 부팅/이미지 생성 시간, GitHub Runner 네트워크에 따라 달라질 수 있음.
- `workflow_dispatch`의 `skip_cleanup: true`는 디버깅 시에만 사용하고, 평소에는 리소스 정리 유지 권장.
