# Rate Limiting 및 모니터링 구현 완료

## 구현 개요

Rate Limiting과 공유 링크 접근 패턴 모니터링이 완료되었습니다.

## 구현 내용

### 1. Rate Limiting 미들웨어

**파일**: `app/middlewares/rate_limit_middleware.py`

**기능**:
- `slowapi`를 사용한 Rate limiting 구현
- IP 기반 요청 제한 (X-Forwarded-For, X-Real-IP 지원)
- 엔드포인트별 다른 제한 설정 가능
- Rate limit 초과 시 Prometheus 메트릭 수집 및 로깅

**설정** (환경 변수):
```bash
RATE_LIMIT_ENABLED=true                    # Rate limiting 활성화
RATE_LIMIT_PER_MINUTE=60                   # 일반 엔드포인트: IP당 분당 60회
RATE_LIMIT_SHARE_PER_MINUTE=10            # 공유 링크: IP당 분당 10회
RATE_LIMIT_IMAGE_PER_MINUTE=120           # 이미지 접근: IP당 분당 120회
RATE_LIMIT_BURST=10                       # 버스트 허용량
```

**적용된 엔드포인트**:
- `/share/{token}`: 분당 10회
- `/share/{token}/photos/{photo_id}/image`: 분당 10회
- `/photos/{photo_id}/image`: 분당 120회 (향후 적용 가능)

### 2. 모니터링 메트릭

**Rate Limiting 메트릭**:
- `photo_api_rate_limit_hits_total`: Rate limit 차단 횟수
- `photo_api_rate_limit_requests_total`: Rate limit 체크 요청 수

**공유 링크 접근 패턴 메트릭**:
- `photo_api_share_link_access_total`: 공유 링크 접근 시도 수
- `photo_api_share_link_brute_force_attempts_total`: 브루트포스 공격 시도 수
- `photo_api_share_link_access_duration_seconds`: 접근 응답 시간
- `photo_api_share_link_image_access_total`: 이미지 접근 패턴

**이미지 접근 패턴 메트릭**:
- `photo_api_image_access_total`: 이미지 접근 시도 수
- `photo_api_image_access_duration_seconds`: 이미지 접근 응답 시간

### 3. Grafana 대시보드

**파일**: `grafana/dashboard-photo-api-security.json`

**주요 패널**:
1. Rate Limit 차단 현황
2. Rate Limit 허용률
3. 엔드포인트별 Rate Limit 차단
4. IP별 Rate Limit 차단 (상위 10개)
5. 공유 링크 접근 현황
6. 브루트포스 공격 시도 (상위 10개 IP)
7. 공유 링크 이미지 접근 패턴
8. 인증된 사용자 vs 공유 링크 이미지 접근
9. 이미지 접근 응답 시간 (P95)
10. 보안 요약

### 4. 알림 규칙

**주요 알림**:
- Rate limit 차단 횟수 과다
- 브루트포스 공격 탐지
- 이미지 접근 성능 저하
- 공유 링크 접근 실패율 증가

## 사용 방법

### 1. 환경 변수 설정

```bash
# Rate limiting 활성화
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_SHARE_PER_MINUTE=10
RATE_LIMIT_IMAGE_PER_MINUTE=120
```

### 2. Grafana 대시보드 임포트

1. Grafana 웹 UI 접속
2. 대시보드 → Import
3. `grafana/dashboard-photo-api-security.json` 파일 업로드
4. Prometheus 데이터 소스 선택
5. 대시보드 저장

### 3. 알림 규칙 설정

`MONITORING_VISUALIZATION.md` 파일의 Alertmanager 설정을 참고하여 알림 규칙을 추가하세요.

## 모니터링 지표 해석

### Rate Limiting 지표

**정상 범위**:
- Rate limit 차단률: 5% 미만
- 허용률: 90% 이상

**주의 필요**:
- Rate limit 차단률: 5-10%
- 허용률: 80-90%

**위험**:
- Rate limit 차단률: 10% 이상
- 허용률: 80% 미만

### 공유 링크 접근 패턴

**정상 범위**:
- 무효한 토큰 시도: 분당 10회 미만
- 브루트포스 시도율: 1% 미만

**주의 필요**:
- 무효한 토큰 시도: 분당 10-50회
- 브루트포스 시도율: 1-5%

**위험**:
- 무효한 토큰 시도: 분당 50회 이상
- 브루트포스 시도율: 5% 이상

### 이미지 접근 성능

**정상 범위**:
- P95 응답 시간: 1초 미만
- 성공률: 95% 이상

**주의 필요**:
- P95 응답 시간: 1-2초
- 성공률: 90-95%

**위험**:
- P95 응답 시간: 2초 이상
- 성공률: 90% 미만

## 문제 해결

### Rate limit이 너무 자주 차단되는 경우

1. `RATE_LIMIT_PER_MINUTE` 값을 증가
2. 특정 IP의 정상적인 사용 패턴 확인
3. DDoS 공격 여부 확인

### 브루트포스 공격이 탐지된 경우

1. 해당 IP의 활동 로그 확인
2. 필요시 IP 차단 (방화벽 또는 WAF)
3. Rate limit 설정 조정

### 이미지 접근 성능이 저하되는 경우

1. CDN 설정 확인
2. Object Storage 성능 확인
3. 네트워크 지연 확인

## 참고 문서

- [MONITORING_VISUALIZATION.md](./MONITORING_VISUALIZATION.md): 상세한 모니터링 가이드
- [SECURITY_AUDIT.md](./SECURITY_AUDIT.md): 보안 검토 결과
- [CDN_SECURITY.md](./CDN_SECURITY.md): CDN 보안 가이드

