# 고가용성 모니터링 지표 및 대시보드 가이드

## 개요

이 문서는 Photo API 서비스의 고가용성(High Availability)을 보장하기 위한 핵심 모니터링 지표를 정의하고, 대시보드 구성 및 알림 기준을 제시합니다.

**모니터링 목표:**
- 서비스 가용성 99.9% 이상 유지
- 장애 조기 탐지 및 대응 시간 단축
- 성능 병목 지점 사전 식별
- 보안 위협 실시간 탐지
- 리소스 사용량 최적화

---

## 1. 가용성 지표 (Availability Metrics)

### 1.1 서비스 상태 (Service Health)

#### `photo_api_ready`
- **타입**: Gauge
- **설명**: 애플리케이션 준비 상태 (1=정상, 0=종료 중)
- **구현 방식**: 
  - 애플리케이션 시작 시 `ready.set(1)`
  - 종료 시 `ready.set(0)`
  - `/health` 엔드포인트와 연동하여 헬스체크에 활용
- **핵심 모니터링 포인트**:
  - 값이 0이면 서비스가 종료 중이거나 장애 상태
  - 여러 인스턴스 중 일부가 0이면 해당 인스턴스 제거 필요
- **알림 기준**:
  - **Warning**: 값이 0이고 30초 이상 지속
  - **Critical**: 값이 0이고 1분 이상 지속 (즉시 대응 필요)

#### `photo_api_app_info`
- **타입**: Gauge (라벨만 사용, 값은 항상 1)
- **설명**: 애플리케이션 및 노드 식별 정보
- **라벨**: `node`, `app`, `version`, `environment`
- **구현 방식**: 
  - 애플리케이션 시작 시 한 번 설정
  - 노드별, 버전별 메트릭 필터링에 활용
- **핵심 모니터링 포인트**:
  - 노드별 서비스 상태 확인
  - 버전 배포 상태 추적
  - 환경별(dev/staging/prod) 메트릭 분리
- **알림 기준**: 알림 대상 아님 (정보성 메트릭)

---

## 2. 성능 지표 (Performance Metrics)

### 2.1 요청 처리 성능

#### `http_request_duration_seconds` (FastAPI Instrumentator)
- **타입**: Histogram
- **설명**: HTTP 요청 처리 시간 (FastAPI Instrumentator 자동 수집)
- **버킷**: `0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0`
- **라벨**: `method`, `handler`, `status`
- **구현 방식**: FastAPI Instrumentator가 자동으로 수집
- **핵심 모니터링 포인트**:
  - **P50 (중앙값)**: 일반적인 사용자 경험
  - **P95**: 95% 사용자가 경험하는 응답 시간
  - **P99**: 최악의 경우 대응 기준
  - 엔드포인트별 성능 비교
  - HTTP 메서드별 성능 분석
- **알림 기준**:
  - **Warning**: P95 > 1초 지속 5분 이상
  - **Critical**: P95 > 3초 지속 2분 이상 또는 P99 > 5초

#### `http_requests_total` (FastAPI Instrumentator)
- **타입**: Counter
- **설명**: 총 HTTP 요청 수
- **라벨**: `method`, `handler`, `status`
- **구현 방식**: FastAPI Instrumentator가 자동으로 수집
- **핵심 모니터링 포인트**:
  - 요청 처리량 (RPS: Requests Per Second)
  - HTTP 상태 코드별 분포 (2xx, 4xx, 5xx)
  - 엔드포인트별 트래픽 패턴
  - 시간대별 트래픽 분석
- **알림 기준**:
  - **Warning**: 5xx 에러율 > 1% 지속 5분
  - **Critical**: 5xx 에러율 > 5% 지속 2분 또는 요청 처리량 급증 (DDoS 가능성)

### 2.2 핵심 비즈니스 로직 성능

#### `photo_api_login_duration_seconds`
- **타입**: Histogram
- **설명**: 로그인 요청 처리 시간
- **라벨**: `result` (success | failure)
- **버킷**: `0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 3.0, 5.0`
- **구현 방식**: 
  - `/auth/login` 엔드포인트에서 수동 측정
  - `time.perf_counter()`로 시작/종료 시간 측정
  - 성공/실패별로 분리하여 수집
- **핵심 모니터링 포인트**:
  - 로그인 성능 저하 탐지 (비밀번호 해싱, DB 조회 병목)
  - 실패한 로그인 시도 처리 시간 (보안 공격 탐지)
  - 사용자 인증 경험 품질
- **알림 기준**:
  - **Warning**: P95 > 1초 지속 5분
  - **Critical**: P95 > 3초 지속 2분

#### `photo_api_image_access_duration_seconds`
- **타입**: Histogram
- **설명**: 이미지 접근 요청 처리 시간
- **라벨**: `access_type` (authenticated | shared), `result` (success | denied)
- **버킷**: `0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0`
- **구현 방식**: 
  - `/photos/{id}/image` 및 `/share/{token}/photos/{id}/image` 엔드포인트에서 측정
  - CDN 리다이렉트 vs 백엔드 스트리밍 성능 비교
- **핵심 모니터링 포인트**:
  - 이미지 로딩 성능 (핵심 사용자 경험)
  - CDN 효과 측정 (리다이렉트 시간)
  - Object Storage 다운로드 성능
  - 인증된 사용자 vs 공유 링크 성능 비교
- **알림 기준**:
  - **Warning**: P95 > 2초 지속 5분
  - **Critical**: P95 > 5초 지속 2분

#### `photo_api_share_link_access_duration_seconds`
- **타입**: Histogram
- **설명**: 공유 링크 접근 요청 처리 시간
- **라벨**: `token_status` (valid | invalid | expired), `result` (success | denied)
- **버킷**: `0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0`
- **구현 방식**: 
  - `/share/{token}` 엔드포인트에서 측정
  - 토큰 검증, DB 조회, 앨범 조회 시간 포함
- **핵심 모니터링 포인트**:
  - 공유 링크 접근 성능
  - 토큰 검증 성능 (DB 쿼리 최적화 필요 여부)
  - 무효한 토큰 처리 시간 (보안 공격 탐지)
- **알림 기준**:
  - **Warning**: P95 > 1초 지속 5분
  - **Critical**: P95 > 3초 지속 2분

#### `photo_api_external_request_duration_seconds`
- **타입**: Histogram
- **설명**: 외부 서비스 요청 처리 시간 (Object Storage, CDN, Log Service)
- **라벨**: `service` (object_storage | cdn | log_service)
- **버킷**: `0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0`
- **구현 방식**: 
  - `record_external_request()` 컨텍스트 매니저 사용
  - 외부 API 호출 전후 시간 측정
- **핵심 모니터링 포인트**:
  - 외부 의존성 서비스 응답 시간
  - Object Storage 업로드/다운로드 성능
  - CDN 토큰 생성 성능
  - Log Service 전송 성능
- **알림 기준**:
  - **Warning**: P95 > 2초 지속 5분
  - **Critical**: P95 > 5초 지속 2분 또는 특정 서비스 완전 실패

### 2.3 동시성 및 처리량

#### `photo_api_active_sessions`
- **타입**: Gauge
- **설명**: 현재 처리 중인 인증된 요청 수 (JWT 기반)
- **구현 방식**: 
  - `ActiveSessionsMiddleware`에서 요청 시작 시 증가, 종료 시 감소
  - JWT 인증이 성공한 요청만 카운트
- **핵심 모니터링 포인트**:
  - 동시 사용자 수 추적
  - 서버 부하 예측 (동시 요청 수 증가 시 성능 저하 가능)
  - 리소스 사용량과의 상관관계 분석
- **알림 기준**:
  - **Warning**: 값이 100 이상 지속 10분 (단일 인스턴스 기준)
  - **Critical**: 값이 200 이상 지속 5분 (과부하 가능성)

---

## 3. 안정성 지표 (Stability Metrics)

### 3.1 에러 및 예외

#### `photo_api_exceptions_total`
- **타입**: Counter
- **설명**: 처리되지 않은 예외 총 수
- **구현 방식**: 
  - Global exception handler에서 수집
  - 예상치 못한 예외 발생 시 증가
- **핵심 모니터링 포인트**:
  - 예외 발생 빈도 및 트렌드
  - 예외 발생 시점과 다른 메트릭의 상관관계
  - 코드 버그 또는 환경 문제 탐지
- **알림 기준**:
  - **Warning**: 분당 10회 이상 지속 5분
  - **Critical**: 분당 50회 이상 지속 2분

#### `photo_api_db_errors_total`
- **타입**: Counter
- **설명**: 데이터베이스 세션/트랜잭션 에러 총 수
- **구현 방식**: 
  - `get_db()` dependency에서 DB 에러 발생 시 증가
  - 커밋/롤백 실패, 연결 풀 고갈 등 포함
- **핵심 모니터링 포인트**:
  - DB 연결 풀 상태 (연결 풀 고갈 탐지)
  - 트랜잭션 실패율
  - DB 서버 장애 조기 탐지
- **알림 기준**:
  - **Warning**: 분당 5회 이상 지속 5분
  - **Critical**: 분당 20회 이상 지속 2분 또는 DB 연결 불가

#### `photo_api_external_request_errors_total`
- **타입**: Counter
- **설명**: 외부 API 요청 실패 총 수
- **라벨**: `service` (object_storage | cdn | log_service)
- **구현 방식**: 
  - `record_external_request()` 컨텍스트 매니저에서 예외 발생 시 증가
  - 각 외부 서비스별로 분리하여 수집
- **핵심 모니터링 포인트**:
  - 외부 의존성 서비스 상태
  - Object Storage 장애 (파일 업로드/다운로드 실패)
  - CDN 장애 (토큰 생성 실패)
  - Log Service 장애 (로깅 실패)
- **알림 기준**:
  - **Warning**: 특정 서비스 에러율 > 5% 지속 5분
  - **Critical**: 특정 서비스 에러율 > 20% 지속 2분 또는 완전 실패

### 3.2 로깅 시스템 상태

#### `photo_api_log_queue_size`
- **타입**: Gauge (Custom Collector)
- **설명**: NHN Log Service 전송 대기 중인 로그 큐 크기
- **구현 방식**: 
  - `LogQueueSizeCollector`에서 NHN Logger Service의 큐 크기 조회
  - 백프레셔(backpressure) 지표
- **핵심 모니터링 포인트**:
  - 로그 전송 지연 탐지
  - Log Service 장애 또는 네트워크 문제 탐지
  - 메모리 사용량 증가 가능성 (큐가 계속 쌓이면)
- **알림 기준**:
  - **Warning**: 큐 크기 > 1000 지속 5분
  - **Critical**: 큐 크기 > 5000 지속 2분 (메모리 부족 위험)

---

## 4. 보안 지표 (Security Metrics)

### 4.1 Rate Limiting

#### `photo_api_rate_limit_hits_total`
- **타입**: Counter
- **설명**: Rate limit에 걸린 요청 수 (차단된 요청)
- **라벨**: `endpoint`, `client_id` (IP 주소 일부)
- **구현 방식**: 
  - `RateLimitExceeded` 예외 발생 시 증가
  - IP 주소는 개인정보 보호를 위해 일부만 저장
- **핵심 모니터링 포인트**:
  - DDoS 공격 탐지 (급격한 차단 증가)
  - 특정 IP의 과도한 요청 패턴
  - 엔드포인트별 공격 대상 식별
- **알림 기준**:
  - **Warning**: 분당 100회 이상 지속 5분
  - **Critical**: 분당 500회 이상 지속 2분 또는 특정 IP가 분당 200회 이상

#### `photo_api_rate_limit_requests_total`
- **타입**: Counter
- **설명**: Rate limit 체크를 받은 총 요청 수
- **라벨**: `endpoint`, `status` (allowed | blocked)
- **구현 방식**: 
  - Rate limit 미들웨어에서 모든 요청에 대해 수집
  - 허용/차단 상태별로 분리
- **핵심 모니터링 포인트**:
  - Rate limit 적용 범위 확인
  - 허용률 계산: `allowed / total * 100`
  - 차단률이 너무 높으면 Rate limit 설정 조정 필요
- **알림 기준**:
  - **Warning**: 차단률 > 10% 지속 5분
  - **Critical**: 차단률 > 30% 지속 2분

### 4.2 공유 링크 보안

#### `photo_api_share_link_brute_force_attempts_total`
- **타입**: Counter
- **설명**: 브루트포스 공격 시도 횟수 (무효한 토큰 시도)
- **라벨**: `client_id` (IP 주소 일부)
- **구현 방식**: 
  - 공유 링크 접근 시 무효한 토큰이면 증가
  - IP별로 분리하여 수집
- **핵심 모니터링 포인트**:
  - 브루트포스 공격 실시간 탐지
  - 특정 IP의 의심스러운 활동
  - 공유 링크 보안 위협 평가
- **알림 기준**:
  - **Warning**: 분당 50회 이상 지속 5분
  - **Critical**: 분당 100회 이상 지속 2분 또는 특정 IP가 분당 200회 이상

#### `photo_api_share_link_access_total`
- **타입**: Counter
- **설명**: 공유 링크 접근 시도 총 수
- **라벨**: `token_status` (valid | invalid | expired), `result` (success | denied)
- **구현 방식**: 
  - 공유 링크 접근 시 토큰 상태 및 결과별로 수집
  - 정상 사용 vs 공격 시도 구분
- **핵심 모니터링 포인트**:
  - 공유 링크 사용 패턴 분석
  - 무효한 토큰 시도 비율 (보안 위협 지표)
  - 만료된 토큰 접근 시도 (사용자 경험)
- **알림 기준**:
  - **Warning**: 무효한 토큰 비율 > 20% 지속 5분
  - **Critical**: 무효한 토큰 비율 > 50% 지속 2분

#### `photo_api_share_link_image_access_total`
- **타입**: Counter
- **설명**: 공유 링크를 통한 이미지 접근 시도 수
- **라벨**: `token_status`, `photo_in_album` (yes | no)
- **구현 방식**: 
  - 공유 링크 이미지 접근 시 수집
  - 앨범에 포함되지 않은 사진 접근 시도 탐지
- **핵심 모니터링 포인트**:
  - 다른 앨범 사진 접근 시도 (보안 이슈)
  - 정상적인 이미지 접근 패턴
- **알림 기준**:
  - **Warning**: `photo_in_album="no"` 접근이 분당 10회 이상 지속 5분
  - **Critical**: `photo_in_album="no"` 접근이 분당 50회 이상 지속 2분

### 4.3 이미지 접근 보안

#### `photo_api_image_access_total`
- **타입**: Counter
- **설명**: 이미지 접근 시도 총 수
- **라벨**: `access_type` (authenticated | shared), `result` (success | denied)
- **구현 방식**: 
  - 이미지 접근 엔드포인트에서 수집
  - 인증된 사용자 vs 공유 링크 구분
- **핵심 모니터링 포인트**:
  - 이미지 접근 패턴 분석
  - 접근 거부율 (권한 위반 탐지)
  - 인증된 사용자 vs 공유 링크 비율
- **알림 기준**:
  - **Warning**: 거부율 > 10% 지속 5분
  - **Critical**: 거부율 > 30% 지속 2분

---

## 5. 리소스 사용량 지표 (Resource Metrics)

### 5.1 시스템 리소스 (node_exporter)

#### `node_cpu_seconds_total`
- **타입**: Counter
- **설명**: CPU 사용 시간 (초)
- **구현 방식**: node_exporter가 자동 수집
- **핵심 모니터링 포인트**:
  - CPU 사용률: `rate(node_cpu_seconds_total[5m])`
  - CPU 부하와 응답 시간의 상관관계
  - CPU 병목 지점 식별
- **알림 기준**:
  - **Warning**: CPU 사용률 > 80% 지속 10분
  - **Critical**: CPU 사용률 > 95% 지속 5분

#### `node_memory_MemAvailable_bytes`
- **타입**: Gauge
- **설명**: 사용 가능한 메모리 (바이트)
- **구현 방식**: node_exporter가 자동 수집
- **핵심 모니터링 포인트**:
  - 메모리 사용률: `(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100`
  - 메모리 부족으로 인한 OOM(Out of Memory) 위험 탐지
  - 로그 큐 크기와의 상관관계
- **알림 기준**:
  - **Warning**: 메모리 사용률 > 85% 지속 10분
  - **Critical**: 메모리 사용률 > 95% 지속 5분 또는 사용 가능 메모리 < 100MB

#### `node_filesystem_avail_bytes`
- **타입**: Gauge
- **설명**: 파일시스템 사용 가능 공간 (바이트)
- **라벨**: `device`, `fstype`, `mountpoint`
- **구현 방식**: node_exporter가 자동 수집
- **핵심 모니터링 포인트**:
  - 디스크 사용률: `(1 - node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100`
  - 디스크 공간 부족 위험 탐지
  - 로그 파일, 임시 파일 누적 확인
- **알림 기준**:
  - **Warning**: 디스크 사용률 > 80% 지속 10분
  - **Critical**: 디스크 사용률 > 90% 지속 5분 또는 사용 가능 공간 < 1GB

#### `node_network_receive_bytes_total` / `node_network_transmit_bytes_total`
- **타입**: Counter
- **설명**: 네트워크 수신/송신 바이트 수
- **구현 방식**: node_exporter가 자동 수집
- **핵심 모니터링 포인트**:
  - 네트워크 대역폭 사용률
  - 이미지 업로드/다운로드 트래픽 추적
  - DDoS 공격 탐지 (비정상적인 트래픽 증가)
- **알림 기준**:
  - **Warning**: 네트워크 사용률이 평소 대비 200% 이상 지속 10분
  - **Critical**: 네트워크 사용률이 평소 대비 500% 이상 지속 5분

---

## 6. 비즈니스 지표 (Business Metrics)

### 6.1 사용자 활동

#### `http_requests_total{handler="/auth/register"}`
- **타입**: Counter
- **설명**: 회원가입 요청 수
- **구현 방식**: FastAPI Instrumentator 자동 수집
- **핵심 모니터링 포인트**:
  - 신규 사용자 증가 추세
  - 회원가입 성공률: `2xx / total * 100`
  - 회원가입 실패 원인 분석 (4xx vs 5xx)
- **알림 기준**:
  - **Warning**: 회원가입 실패율 > 10% 지속 5분
  - **Critical**: 회원가입 실패율 > 30% 지속 2분

#### `http_requests_total{handler="/auth/login"}`
- **타입**: Counter
- **설명**: 로그인 요청 수
- **구현 방식**: FastAPI Instrumentator 자동 수집
- **핵심 모니터링 포인트**:
  - 활성 사용자 수 추정
  - 로그인 성공률: `2xx / total * 100`
  - 로그인 실패 패턴 (무차별 대입 공격 탐지)
- **알림 기준**:
  - **Warning**: 로그인 실패율 > 20% 지속 5분
  - **Critical**: 로그인 실패율 > 50% 지속 2분

### 6.2 사진 관리 활동

#### `http_requests_total{handler="/photos/presigned-url"}`
- **타입**: Counter
- **설명**: Presigned URL 생성 요청 수 (사진 업로드 시작)
- **구현 방식**: FastAPI Instrumentator 자동 수집
- **핵심 모니터링 포인트**:
  - 사진 업로드 활동 추세
  - Presigned URL 생성 성공률
  - 업로드 트래픽 예측
- **알림 기준**:
  - **Warning**: Presigned URL 생성 실패율 > 5% 지속 5분
  - **Critical**: Presigned URL 생성 실패율 > 15% 지속 2분

#### `http_requests_total{handler="/photos/confirm"}`
- **타입**: Counter
- **설명**: 사진 업로드 완료 확인 요청 수
- **구현 방식**: FastAPI Instrumentator 자동 수집
- **핵심 모니터링 포인트**:
  - 실제 업로드 완료 수 (Presigned URL 생성 대비)
  - 업로드 완료율: `confirm / presigned-url * 100`
  - 업로드 실패 원인 분석
- **알림 기준**:
  - **Warning**: 업로드 완료율 < 80% 지속 10분
  - **Critical**: 업로드 완료율 < 60% 지속 5분

#### `http_requests_total{handler=~"/photos/.*image"}`
- **타입**: Counter
- **설명**: 이미지 조회 요청 수
- **구현 방식**: FastAPI Instrumentator 자동 수집
- **핵심 모니터링 포인트**:
  - 이미지 조회 활동 추세
  - CDN 캐시 효율성 평가
  - 이미지 트래픽 예측
- **알림 기준**:
  - **Warning**: 이미지 조회 실패율 > 5% 지속 5분
  - **Critical**: 이미지 조회 실패율 > 15% 지속 2분

---

## 7. 비즈니스 성장 지표 (Business Growth Metrics)

### 7.1 서비스 성장 추적

#### `photo_api_users_total`
- **타입**: Gauge
- **설명**: 전체 회원수 및 활성 회원수
- **라벨**: `status` (total | active)
- **구현 방식**: 
  - 백그라운드 태스크(`business_metrics_loop`)에서 60초마다 DB 집계
  - 회원가입 시 실시간 증가 (`users_total.labels(status="total").inc()`)
- **핵심 모니터링 포인트**:
  - 서비스 성장 추이 (회원수 증가율)
  - 활성 회원 비율 (전체 대비 활성 회원)
  - 회원가입 트렌드 분석
- **대시보드 활용**:
  - Time series: 시간별 회원수 추이
  - Stat: 현재 전체/활성 회원수
  - Growth rate: `rate(photo_api_users_total{status="total"}[1h])`

#### `photo_api_albums_total`
- **타입**: Gauge
- **설명**: 전체 앨범 수 및 공유 앨범 수
- **라벨**: `type` (total | shared)
- **구현 방식**: 
  - 백그라운드 태스크에서 60초마다 DB 집계
  - 앨범 생성 시 실시간 증가 (`albums_total.labels(type="total").inc()`)
- **핵심 모니터링 포인트**:
  - 앨범 생성 추이
  - 공유 앨범 비율 (전체 대비 공유 앨범)
  - 사용자당 평균 앨범 수
- **대시보드 활용**:
  - Time series: 시간별 앨범 수 추이
  - Stat: 현재 전체/공유 앨범 수
  - 공유율: `photo_api_albums_total{type="shared"} / photo_api_albums_total{type="total"} * 100`

#### `photo_api_photos_total`
- **타입**: Gauge
- **설명**: 전체 사진 수
- **구현 방식**: 
  - 백그라운드 태스크에서 60초마다 DB 집계
  - 사진 업로드 확인 시 실시간 증가 (`photos_total.inc()`)
- **핵심 모니터링 포인트**:
  - 사진 업로드 추이
  - 사용자당 평균 사진 수
  - 앨범당 평균 사진 수
- **대시보드 활용**:
  - Time series: 시간별 사진 수 추이
  - Stat: 현재 전체 사진 수
  - 업로드 속도: `rate(photo_api_photos_total[1h])`

#### `photo_api_share_links_total`
- **타입**: Gauge
- **설명**: 전체 공유 링크 수 및 활성 공유 링크 수
- **라벨**: `status` (total | active)
- **구현 방식**: 
  - 백그라운드 태스크에서 60초마다 DB 집계
  - 공유 링크 생성 시 실시간 증가 (`share_links_total.labels(status="total").inc()`)
- **핵심 모니터링 포인트**:
  - 공유 링크 생성 추이
  - 활성 공유 링크 비율
  - 공유 기능 사용률
- **대시보드 활용**:
  - Time series: 시간별 공유 링크 수 추이
  - Stat: 현재 전체/활성 공유 링크 수

### 7.2 Object Storage 사용량 추적

#### `photo_api_object_storage_usage_bytes`
- **타입**: Gauge
- **설명**: 전체 Object Storage 사용량 (바이트)
- **구현 방식**: 
  - 백그라운드 태스크에서 60초마다 DB 집계 (모든 사진의 `file_size` 합계)
  - 사진 업로드 확인 시 실시간 증가 (`object_storage_usage_bytes.inc(photo.file_size)`)
- **핵심 모니터링 포인트**:
  - **용량 급증 탐지**: 갑자기 사용량이 늘어났는지 확인
  - **비용 관리**: Object Storage 비용 예측
  - **성장 추이**: 시간별 사용량 증가율
- **대시보드 활용**:
  - Time series: 시간별 사용량 추이 (GB 단위로 변환)
  - Stat: 현재 사용량 (GB)
  - 증가율: `rate(photo_api_object_storage_usage_bytes[1h])`
  - **알림 기준**:
    - **Warning**: 1시간 내 10% 이상 증가
    - **Critical**: 1시간 내 50% 이상 증가 (비정상적 업로드 가능성)

#### `photo_api_object_storage_usage_by_user_bytes`
- **타입**: Gauge
- **설명**: 사용자별 Object Storage 사용량 (바이트)
- **라벨**: `user_id` (사용자 ID)
- **구현 방식**: 
  - 백그라운드 태스크에서 60초마다 DB 집계 (사용자별 `file_size` 합계)
  - 사진 업로드 확인 시 실시간 증가 (`object_storage_usage_by_user_bytes.labels(user_id=str(user_id)).inc(photo.file_size)`)
- **핵심 모니터링 포인트**:
  - **누가 많이 올렸는지**: 상위 사용자 식별
  - **이상 사용자 탐지**: 특정 사용자가 비정상적으로 많은 용량 사용
  - **사용자별 사용량 분포**: 대부분의 용량을 소수의 사용자가 사용하는지 확인
- **대시보드 활용**:
  - Table: 사용자별 사용량 상위 N개 (user_id, 사용량 GB)
  - Bar chart: 사용자별 사용량 분포
  - **알림 기준**:
    - **Warning**: 특정 사용자가 1시간 내 1GB 이상 업로드
    - **Critical**: 특정 사용자가 1시간 내 10GB 이상 업로드 (비정상적 활동)

#### `photo_api_photo_upload_size_total_bytes`
- **타입**: Counter
- **설명**: 누적 사진 업로드 용량 (시간별 추이 분석용)
- **라벨**: `user_id` (사용자 ID)
- **구현 방식**: 
  - 사진 업로드 확인 시 증가 (`photo_upload_size_total.labels(user_id=str(user_id)).inc(photo.file_size)`)
- **핵심 모니터링 포인트**:
  - **언제부터 용량이 급증했는지**: 시간별 업로드 용량 추이
  - **사용자별 업로드 패턴**: 특정 시간대에 집중 업로드하는 사용자 식별
- **대시보드 활용**:
  - Time series: 시간별 업로드 용량 (rate 기반)
  - Heatmap: 시간 × 사용자별 업로드 용량
  - **쿼리 예시**:
    - 시간별 업로드 용량: `rate(photo_api_photo_upload_size_total_bytes[5m])`
    - 사용자별 시간별 업로드: `sum by (user_id) (rate(photo_api_photo_upload_size_total_bytes[5m]))`

### 7.3 비즈니스 메트릭 수집 방식

**실시간 업데이트:**
- 회원가입, 앨범 생성, 사진 업로드, 공유 링크 생성 시 즉시 메트릭 증가
- Object Storage 사용량도 업로드 시 즉시 반영

**주기적 집계 (백그라운드 태스크):**
- 60초마다 DB에서 전체 집계하여 메트릭 업데이트
- 실시간 업데이트와 주기적 집계를 병행하여 정확성 보장
- DB 집계는 실시간 업데이트가 누락된 경우를 보완

**메트릭 수집 이유:**
1. **서비스 성장 추적**: 회원수, 앨범 수, 사진 수 추이로 서비스 성장률 파악
2. **용량 관리**: Object Storage 사용량 급증 시 조기 탐지 및 비용 관리
3. **이상 탐지**: 특정 사용자의 비정상적 업로드 패턴 탐지
4. **비즈니스 의사결정**: 서비스 성장 데이터를 바탕으로 기능 개발 우선순위 결정

---

## 8. 대시보드 구성 가이드

### 7.1 대시보드 선정 기준

**권장 대시보드 도구: Grafana**

**선정 이유:**
1. **Prometheus 통합**: Prometheus 메트릭을 직접 쿼리 가능
2. **실시간 모니터링**: 30초 이내 리프레시 지원
3. **다양한 시각화**: Time series, Stat, Table, Bar chart 등
4. **알림 연동**: Alertmanager와 연동하여 알림 규칙 설정 가능
5. **대시보드 공유**: JSON 형식으로 대시보드 공유 및 버전 관리 가능

### 7.2 대시보드 패널 구성

#### Row 1: 서비스 상태 요약 (Service Health Overview)
- **패널 1**: 서비스 가용성 (Gauge)
  - 쿼리: `photo_api_ready`
  - 임계값: 0.5 (경고), 0 (위험)
  - 설명: 서비스 준비 상태

- **패널 2**: 활성 인스턴스 수 (Stat)
  - 쿼리: `count(photo_api_ready == 1)`
  - 설명: 정상 동작 중인 인스턴스 수

- **패널 3**: 요청 처리량 (Stat)
  - 쿼리: `sum(rate(http_requests_total[5m])) * 60`
  - 단위: req/min
  - 설명: 분당 요청 처리 수

- **패널 4**: 에러율 (Stat)
  - 쿼리: `sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100`
  - 단위: %
  - 임계값: 1% (경고), 5% (위험)

#### Row 2: 성능 지표 (Performance Metrics)
- **패널 1**: 응답 시간 분포 (Time Series)
  - 쿼리: 
    - P50: `histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))`
    - P95: `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))`
    - P99: `histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))`
  - 단위: 초
  - 설명: 전체 요청 응답 시간 분포

- **패널 2**: 엔드포인트별 응답 시간 (Time Series)
  - 쿼리: `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, handler))`
  - 설명: 엔드포인트별 P95 응답 시간

- **패널 3**: 로그인 성능 (Time Series)
  - 쿼리: `histogram_quantile(0.95, sum(rate(photo_api_login_duration_seconds_bucket[5m])) by (le, result))`
  - 설명: 로그인 성공/실패별 응답 시간

- **패널 4**: 이미지 접근 성능 (Time Series)
  - 쿼리: `histogram_quantile(0.95, sum(rate(photo_api_image_access_duration_seconds_bucket[5m])) by (le, access_type))`
  - 설명: 인증된 사용자 vs 공유 링크 이미지 접근 성능

#### Row 3: 안정성 지표 (Stability Metrics)
- **패널 1**: 예외 발생 추이 (Time Series)
  - 쿼리: `rate(photo_api_exceptions_total[5m]) * 60`
  - 단위: exceptions/min
  - 설명: 분당 예외 발생 수

- **패널 2**: DB 에러 추이 (Time Series)
  - 쿼리: `rate(photo_api_db_errors_total[5m]) * 60`
  - 단위: errors/min
  - 설명: 분당 DB 에러 수

- **패널 3**: 외부 서비스 에러 (Time Series)
  - 쿼리: `rate(photo_api_external_request_errors_total[5m]) * 60`
  - 라벨: `service`
  - 단위: errors/min
  - 설명: 외부 서비스별 에러 발생 수

- **패널 4**: 로그 큐 크기 (Time Series)
  - 쿼리: `photo_api_log_queue_size`
  - 설명: 로그 전송 대기 큐 크기

#### Row 4: 보안 지표 (Security Metrics)
- **패널 1**: Rate Limit 차단 추이 (Time Series)
  - 쿼리: `rate(photo_api_rate_limit_hits_total[5m]) * 60`
  - 단위: blocks/min
  - 설명: 분당 Rate limit 차단 수

- **패널 2**: 브루트포스 공격 시도 (Time Series)
  - 쿼리: `rate(photo_api_share_link_brute_force_attempts_total[5m]) * 60`
  - 단위: attempts/min
  - 설명: 분당 브루트포스 공격 시도 수

- **패널 3**: 공유 링크 접근 패턴 (Time Series)
  - 쿼리: `rate(photo_api_share_link_access_total[5m]) * 60`
  - 라벨: `token_status`, `result`
  - 단위: accesses/min
  - 설명: 토큰 상태별 공유 링크 접근 수

- **패널 4**: 의심스러운 IP 활동 (Table)
  - 쿼리: `topk(10, sum by (client_id) (rate(photo_api_rate_limit_hits_total[5m])) * 60)`
  - 설명: Rate limit 차단이 많은 상위 10개 IP

#### Row 5: 리소스 사용량 (Resource Usage)
- **패널 1**: CPU 사용률 (Time Series)
  - 쿼리: `100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)`
  - 단위: %
  - 설명: CPU 사용률

- **패널 2**: 메모리 사용률 (Time Series)
  - 쿼리: `(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100`
  - 단위: %
  - 설명: 메모리 사용률

- **패널 3**: 디스크 사용률 (Time Series)
  - 쿼리: `(1 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})) * 100`
  - 단위: %
  - 설명: 루트 파일시스템 사용률

- **패널 4**: 네트워크 트래픽 (Time Series)
  - 쿼리: 
    - 수신: `rate(node_network_receive_bytes_total[5m]) * 8 / 1024 / 1024`
    - 송신: `rate(node_network_transmit_bytes_total[5m]) * 8 / 1024 / 1024`
  - 단위: Mbps
  - 설명: 네트워크 대역폭 사용량

#### Row 6: 비즈니스 지표 (Business Metrics)
- **패널 1**: 회원가입 추이 (Time Series)
  - 쿼리: `rate(http_requests_total{handler="/auth/register",status=~"2.."}[5m]) * 60`
  - 단위: registrations/min
  - 설명: 분당 회원가입 성공 수

- **패널 2**: 로그인 추이 (Time Series)
  - 쿼리: `rate(http_requests_total{handler="/auth/login",status=~"2.."}[5m]) * 60`
  - 단위: logins/min
  - 설명: 분당 로그인 성공 수

- **패널 3**: 사진 업로드 추이 (Time Series)
  - 쿼리: `rate(http_requests_total{handler="/photos/confirm",status=~"2.."}[5m]) * 60`
  - 단위: uploads/min
  - 설명: 분당 사진 업로드 완료 수

- **패널 4**: 이미지 조회 추이 (Time Series)
  - 쿼리: `rate(http_requests_total{handler=~"/photos/.*image",status=~"2.."}[5m]) * 60`
  - 단위: views/min
  - 설명: 분당 이미지 조회 수

### 7.3 대시보드 설정

- **리프레시 간격**: 30초 (실시간 모니터링)
- **시간 범위**: 최근 1시간 (기본), 최근 6시간, 최근 24시간 선택 가능
- **변수 (Variables)**:
  - `instance`: 인스턴스 선택 (다중 인스턴스 환경)
  - `endpoint`: 엔드포인트 필터링
  - `service`: 외부 서비스 필터링

---

## 9. 알림 규칙 (Alert Rules)

### 9.1 Prometheus Alertmanager 설정

```yaml
groups:
  - name: photo_api_availability
    interval: 30s
    rules:
      # 서비스 다운
      - alert: ServiceDown
        expr: photo_api_ready == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Photo API 서비스가 다운되었습니다"
          description: "인스턴스 {{$labels.instance}}의 서비스가 1분 이상 다운 상태입니다."

      # 높은 에러율
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m]))
          /
          sum(rate(http_requests_total[5m])) * 100 > 5
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "높은 에러율 감지"
          description: "5xx 에러율이 {{$value}}%로 5%를 초과했습니다."

  - name: photo_api_performance
    interval: 30s
    rules:
      # 느린 응답 시간
      - alert: SlowResponseTime
        expr: |
          histogram_quantile(0.95, 
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
          ) > 3
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "응답 시간이 느립니다"
          description: "P95 응답 시간이 {{$value}}초로 3초를 초과했습니다."

      # 느린 로그인
      - alert: SlowLogin
        expr: |
          histogram_quantile(0.95,
            sum(rate(photo_api_login_duration_seconds_bucket{result="success"}[5m])) by (le)
          ) > 3
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "로그인 응답 시간이 느립니다"
          description: "로그인 P95 응답 시간이 {{$value}}초로 3초를 초과했습니다."

      # 느린 이미지 접근
      - alert: SlowImageAccess
        expr: |
          histogram_quantile(0.95,
            sum(rate(photo_api_image_access_duration_seconds_bucket{result="success"}[5m])) by (le)
          ) > 5
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "이미지 접근 응답 시간이 느립니다"
          description: "이미지 접근 P95 응답 시간이 {{$value}}초로 5초를 초과했습니다."

  - name: photo_api_stability
    interval: 30s
    rules:
      # 예외 발생 증가
      - alert: HighExceptionRate
        expr: rate(photo_api_exceptions_total[5m]) * 60 > 50
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "예외 발생률이 높습니다"
          description: "분당 {{$value}}개의 예외가 발생하고 있습니다."

      # DB 에러 증가
      - alert: HighDBErrorRate
        expr: rate(photo_api_db_errors_total[5m]) * 60 > 20
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "DB 에러 발생률이 높습니다"
          description: "분당 {{$value}}개의 DB 에러가 발생하고 있습니다."

      # 외부 서비스 장애
      - alert: ExternalServiceFailure
        expr: |
          rate(photo_api_external_request_errors_total[5m]) * 60 > 10
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "외부 서비스 장애 감지"
          description: "{{$labels.service}} 서비스에서 분당 {{$value}}개의 에러가 발생하고 있습니다."

      # 로그 큐 백프레셔
      - alert: LogQueueBackpressure
        expr: photo_api_log_queue_size > 5000
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "로그 큐 백프레셔 발생"
          description: "로그 큐 크기가 {{$value}}로 증가했습니다. Log Service 장애 가능성이 있습니다."

  - name: photo_api_security
    interval: 30s
    rules:
      # DDoS 공격 가능성
      - alert: PossibleDDoSAttack
        expr: rate(photo_api_rate_limit_hits_total[5m]) * 60 > 500
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "DDoS 공격 가능성 감지"
          description: "분당 {{$value}}개의 요청이 Rate limit에 차단되고 있습니다."

      # 브루트포스 공격
      - alert: BruteForceAttack
        expr: rate(photo_api_share_link_brute_force_attempts_total[5m]) * 60 > 100
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "브루트포스 공격 탐지"
          description: "분당 {{$value}}개의 브루트포스 공격 시도가 감지되었습니다."

      # 의심스러운 IP 활동
      - alert: SuspiciousIPActivity
        expr: |
          sum by (client_id) (rate(photo_api_rate_limit_hits_total[5m])) * 60 > 200
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "의심스러운 IP 활동 감지"
          description: "IP {{$labels.client_id}}에서 분당 {{$value}}개의 요청이 차단되고 있습니다."

  - name: photo_api_resources
    interval: 30s
    rules:
      # 높은 CPU 사용률
      - alert: HighCPUUsage
        expr: |
          100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 95
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "CPU 사용률이 높습니다"
          description: "CPU 사용률이 {{$value}}%로 95%를 초과했습니다."

      # 높은 메모리 사용률
      - alert: HighMemoryUsage
        expr: |
          (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > 95
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "메모리 사용률이 높습니다"
          description: "메모리 사용률이 {{$value}}%로 95%를 초과했습니다. OOM 위험이 있습니다."

      # 디스크 공간 부족
      - alert: LowDiskSpace
        expr: |
          (1 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})) * 100 > 90
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "디스크 공간이 부족합니다"
          description: "디스크 사용률이 {{$value}}%로 90%를 초과했습니다."
```

### 9.2 알림 채널 설정

**권장 알림 채널:**
1. **Slack**: 개발팀 채널에 실시간 알림
2. **PagerDuty / Opsgenie**: Critical 알림은 온콜 엔지니어에게 전화/문자
3. **이메일**: Warning 알림은 이메일로 요약 전송

**알림 우선순위:**
- **Critical**: 즉시 대응 필요 (서비스 다운, 높은 에러율, 보안 공격)
- **Warning**: 모니터링 필요 (성능 저하, 리소스 사용률 증가)

---

## 10. 핵심 모니터링 체크리스트

### 10.1 실시간 모니터링 (24/7)

**매 시간 확인:**
- [ ] 서비스 가용성 (`photo_api_ready == 1`)
- [ ] 에러율 (< 1%)
- [ ] 응답 시간 (P95 < 1초)
- [ ] Critical 알림 확인

**매일 확인:**
- [ ] 리소스 사용률 트렌드 (CPU, 메모리, 디스크)
- [ ] 보안 이벤트 (Rate limit, 브루트포스 공격)
- [ ] 외부 서비스 상태 (Object Storage, CDN, Log Service)
- [ ] 비즈니스 지표 트렌드 (회원가입, 로그인, 업로드)

### 10.2 주간 리뷰

- [ ] 알림 규칙 최적화 (False positive 제거)
- [ ] 대시보드 개선 (필요한 지표 추가/제거)
- [ ] 성능 트렌드 분석 (응답 시간, 처리량)
- [ ] 보안 이벤트 리뷰 (공격 패턴 분석)

### 10.3 월간 리뷰

- [ ] SLA 달성 여부 확인 (가용성 99.9% 목표)
- [ ] 리소스 사용량 최적화 (스케일링 필요 여부)
- [ ] 메트릭 수집 정확성 검증
- [ ] 모니터링 시스템 비용 분석

---

## 11. 메트릭 구현 우선순위

### Phase 1: 필수 지표 (즉시 구현)
1. ✅ 서비스 상태 (`photo_api_ready`)
2. ✅ 요청 처리 성능 (`http_request_duration_seconds`)
3. ✅ 에러 및 예외 (`photo_api_exceptions_total`, `photo_api_db_errors_total`)
4. ✅ Rate Limiting (`photo_api_rate_limit_hits_total`)
5. ✅ 리소스 사용량 (node_exporter)

### Phase 2: 중요 지표 (1주일 내)
1. ✅ 로그인 성능 (`photo_api_login_duration_seconds`)
2. ✅ 이미지 접근 성능 (`photo_api_image_access_duration_seconds`)
3. ✅ 공유 링크 보안 (`photo_api_share_link_brute_force_attempts_total`)
4. ✅ 외부 서비스 에러 (`photo_api_external_request_errors_total`)
5. ✅ 로그 큐 크기 (`photo_api_log_queue_size`)

### Phase 3: 추가 지표 (선택적)
1. ✅ 활성 세션 수 (`photo_api_active_sessions`)
2. ✅ 공유 링크 접근 패턴 (`photo_api_share_link_access_total`)
3. ✅ 이미지 접근 패턴 (`photo_api_image_access_total`)

### Phase 4: 비즈니스 성장 지표 (서비스 성장 추적)
1. ✅ 회원수 (`photo_api_users_total`)
2. ✅ 앨범 수 (`photo_api_albums_total`)
3. ✅ 사진 수 (`photo_api_photos_total`)
4. ✅ 공유 링크 수 (`photo_api_share_links_total`)
5. ✅ Object Storage 사용량 (`photo_api_object_storage_usage_bytes`)
6. ✅ 사용자별 Object Storage 사용량 (`photo_api_object_storage_usage_by_user_bytes`)

---

## 12. 참고 자료

- [Prometheus 공식 문서](https://prometheus.io/docs/)
- [Grafana 대시보드 가이드](https://grafana.com/docs/grafana/latest/dashboards/)
- [Alertmanager 설정 가이드](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Prometheus 쿼리 가이드](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [node_exporter 메트릭](https://github.com/prometheus/node_exporter)

---

## 13. 결론

이 문서에서 정의한 모니터링 지표를 통해 Photo API 서비스의 고가용성을 보장할 수 있습니다. 

**핵심 포인트:**
1. **가용성**: 서비스 상태, 에러율, 예외 모니터링
2. **성능**: 응답 시간, 처리량, 핵심 비즈니스 로직 성능
3. **안정성**: DB 에러, 외부 서비스 에러, 로그 시스템 상태
4. **보안**: Rate limiting, 브루트포스 공격, 의심스러운 활동
5. **리소스**: CPU, 메모리, 디스크, 네트워크 사용량
6. **비즈니스**: 사용자 활동, 업로드/다운로드 추세
7. **서비스 성장**: 회원수, 앨범 수, 사진 수, Object Storage 사용량 추이

**다음 단계:**
1. Grafana 대시보드 구성
2. Alertmanager 알림 규칙 설정
3. 알림 채널 연동 (Slack, PagerDuty 등)
4. 모니터링 체크리스트 실행
5. 정기적인 리뷰 및 최적화
