# 모니터링 지표 및 시각화 가이드

## 개요

이 문서는 Rate Limiting과 공유 링크 접근 패턴 모니터링을 위한 지표 정의 및 Grafana 시각화 방법을 설명합니다.

## 수집되는 메트릭

### 1. Rate Limiting 메트릭

#### `photo_api_rate_limit_hits_total`
- **타입**: Counter
- **설명**: Rate limit에 걸린 요청 수 (차단된 요청)
- **레이블**:
  - `endpoint`: 엔드포인트 경로 (예: `/share/{token}`, `/photos/{id}/image`)
  - `client_id`: 클라이언트 IP 주소 일부 (개인정보 보호를 위해 일부만 표시)

**사용 목적**:
- Rate limit 차단 횟수 추적
- 특정 IP의 과도한 요청 패턴 탐지
- DDoS 공격 탐지

#### `photo_api_rate_limit_requests_total`
- **타입**: Counter
- **설명**: Rate limit 체크를 받은 총 요청 수
- **레이블**:
  - `endpoint`: 엔드포인트 경로
  - `status`: `allowed` (허용) 또는 `blocked` (차단)

**사용 목적**:
- Rate limit 적용 범위 확인
- 허용률 계산 (allowed / total)

### 2. 공유 링크 접근 패턴 메트릭

#### `photo_api_share_link_access_total`
- **타입**: Counter
- **설명**: 공유 링크 접근 시도 총 수
- **레이블**:
  - `token_status`: `valid` (유효), `invalid` (무효), `expired` (만료)
  - `result`: `success` (성공), `denied` (거부)

**사용 목적**:
- 공유 링크 사용 패턴 분석
- 무효한 토큰 시도 횟수 추적 (브루트포스 공격 탐지)
- 만료된 토큰 접근 시도 모니터링

#### `photo_api_share_link_brute_force_attempts_total`
- **타입**: Counter
- **설명**: 브루트포스 공격 시도 횟수 (무효한 토큰 시도)
- **레이블**:
  - `client_id`: 클라이언트 IP 주소 일부

**사용 목적**:
- 브루트포스 공격 탐지
- 특정 IP의 의심스러운 활동 모니터링
- 보안 알림 트리거

#### `photo_api_share_link_access_duration_seconds`
- **타입**: Histogram
- **설명**: 공유 링크 접근 요청 처리 시간
- **레이블**:
  - `token_status`: `valid`, `invalid`, `expired`
  - `result`: `success`, `denied`
- **버킷**: `0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0`

**사용 목적**:
- 공유 링크 접근 성능 모니터링
- 느린 응답 시간 탐지
- 병목 지점 식별

#### `photo_api_share_link_image_access_total`
- **타입**: Counter
- **설명**: 공유 링크를 통한 이미지 접근 시도 수
- **레이블**:
  - `token_status`: `valid`, `invalid`, `expired`
  - `photo_in_album`: `yes` (앨범에 포함됨), `no` (앨범에 포함되지 않음)

**사용 목적**:
- 공유 링크 이미지 접근 패턴 분석
- 다른 앨범 사진 접근 시도 탐지
- 이미지 접근 통계

### 3. 이미지 접근 패턴 메트릭

#### `photo_api_image_access_total`
- **타입**: Counter
- **설명**: 이미지 접근 시도 총 수
- **레이블**:
  - `access_type`: `authenticated` (인증된 사용자), `shared` (공유 링크)
  - `result`: `success` (성공), `denied` (거부)

**사용 목적**:
- 이미지 접근 패턴 분석
- 인증된 사용자 vs 공유 링크 사용자 비율
- 접근 거부율 모니터링

#### `photo_api_image_access_duration_seconds`
- **타입**: Histogram
- **설명**: 이미지 접근 요청 처리 시간
- **레이블**:
  - `access_type`: `authenticated`, `shared`
  - `result`: `success`, `denied`
- **버킷**: `0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0`

**사용 목적**:
- 이미지 접근 성능 모니터링
- CDN vs 백엔드 스트리밍 성능 비교
- 응답 시간 이상 탐지

## Grafana 대시보드 구성

### 패널 1: Rate Limiting 개요

**제목**: Rate Limit 차단 현황

**쿼리**:
```promql
# Rate limit 차단 횟수 (분당)
rate(photo_api_rate_limit_hits_total[5m]) * 60

# Rate limit 허용률
sum(rate(photo_api_rate_limit_requests_total{status="allowed"}[5m])) 
/ 
sum(rate(photo_api_rate_limit_requests_total[5m])) * 100
```

**시각화**:
- **타입**: Time series (Graph)
- **Y축**: Count (차단 횟수), Percentage (허용률)
- **범례**: `{{endpoint}}` - `{{client_id}}`

**알림 임계값**:
- Rate limit 차단 횟수가 분당 100회 초과 시 경고
- 허용률이 80% 미만일 때 경고

---

### 패널 2: Rate Limiting 상세 (엔드포인트별)

**제목**: 엔드포인트별 Rate Limit 차단

**쿼리**:
```promql
# 엔드포인트별 차단 횟수
sum by (endpoint) (rate(photo_api_rate_limit_hits_total[5m])) * 60
```

**시각화**:
- **타입**: Bar chart (가로 막대 그래프)
- **정렬**: 값 내림차순
- **범례**: `{{endpoint}}`

**설명**: 어떤 엔드포인트가 가장 많이 차단되는지 확인

---

### 패널 3: Rate Limiting 상세 (IP별)

**제목**: IP별 Rate Limit 차단 (상위 10개)

**쿼리**:
```promql
# IP별 차단 횟수 (상위 10개)
topk(10, sum by (client_id) (rate(photo_api_rate_limit_hits_total[5m])) * 60)
```

**시각화**:
- **타입**: Table
- **컬럼**: client_id, 차단 횟수
- **정렬**: 차단 횟수 내림차순

**설명**: 특정 IP가 과도하게 차단되는 경우 의심스러운 활동 가능성

---

### 패널 4: 공유 링크 접근 패턴

**제목**: 공유 링크 접근 현황

**쿼리**:
```promql
# 토큰 상태별 접근 시도
sum by (token_status) (rate(photo_api_share_link_access_total[5m])) * 60

# 성공률
sum(rate(photo_api_share_link_access_total{result="success"}[5m])) 
/ 
sum(rate(photo_api_share_link_access_total[5m])) * 100
```

**시각화**:
- **타입**: Time series (Graph) + Stat (성공률)
- **범례**: `{{token_status}}` - `{{result}}`

**알림 임계값**:
- 무효한 토큰 시도가 분당 50회 초과 시 경고 (브루트포스 가능성)
- 성공률이 70% 미만일 때 경고

---

### 패널 5: 브루트포스 공격 탐지

**제목**: 브루트포스 공격 시도 (상위 10개 IP)

**쿼리**:
```promql
# IP별 브루트포스 시도 횟수
topk(10, sum by (client_id) (rate(photo_api_share_link_brute_force_attempts_total[5m])) * 60)
```

**시각화**:
- **타입**: Table
- **컬럼**: client_id, 시도 횟수
- **정렬**: 시도 횟수 내림차순
- **조건부 포맷팅**: 
  - 시도 횟수 > 100: 빨간색 배경
  - 시도 횟수 > 50: 노란색 배경

**알림 임계값**:
- 특정 IP가 분당 100회 이상 무효한 토큰 시도 시 즉시 알림

---

### 패널 6: 공유 링크 이미지 접근 패턴

**제목**: 공유 링크 이미지 접근 현황

**쿼리**:
```promql
# 앨범 포함 여부별 이미지 접근
sum by (photo_in_album) (rate(photo_api_share_link_image_access_total[5m])) * 60

# 다른 앨범 사진 접근 시도 (보안 이슈)
sum(rate(photo_api_share_link_image_access_total{photo_in_album="no"}[5m])) * 60
```

**시각화**:
- **타입**: Pie chart (도넛 차트)
- **범례**: `{{photo_in_album}}`

**설명**: 
- `yes`: 정상적인 접근 (해당 앨범에 포함된 사진)
- `no`: 의심스러운 접근 (다른 앨범 사진 접근 시도)

**알림 임계값**:
- `no` 접근이 분당 10회 초과 시 경고

---

### 패널 7: 이미지 접근 패턴 비교

**제목**: 인증된 사용자 vs 공유 링크 이미지 접근

**쿼리**:
```promql
# 접근 타입별 이미지 접근 횟수
sum by (access_type) (rate(photo_api_image_access_total[5m])) * 60

# 접근 타입별 성공률
sum by (access_type) (rate(photo_api_image_access_total{result="success"}[5m])) 
/ 
sum by (access_type) (rate(photo_api_image_access_total[5m])) * 100
```

**시각화**:
- **타입**: Time series (Graph) + Stat (성공률)
- **범례**: `{{access_type}}`

**설명**: 인증된 사용자와 공유 링크 사용자의 이미지 접근 패턴 비교

---

### 패널 8: 이미지 접근 성능

**제목**: 이미지 접근 응답 시간

**쿼리**:
```promql
# 접근 타입별 평균 응답 시간
histogram_quantile(0.95, 
  sum by (le, access_type) (rate(photo_api_image_access_duration_seconds_bucket[5m]))
)

# 접근 타입별 P99 응답 시간
histogram_quantile(0.99, 
  sum by (le, access_type) (rate(photo_api_image_access_duration_seconds_bucket[5m]))
)
```

**시각화**:
- **타입**: Time series (Graph)
- **Y축**: Seconds
- **범례**: `{{access_type}}` - P95 / P99

**알림 임계값**:
- P95 응답 시간이 2초 초과 시 경고
- P99 응답 시간이 5초 초과 시 경고

---

### 패널 9: 공유 링크 접근 성능

**제목**: 공유 링크 접근 응답 시간

**쿼리**:
```promql
# 토큰 상태별 평균 응답 시간
histogram_quantile(0.95, 
  sum by (le, token_status) (rate(photo_api_share_link_access_duration_seconds_bucket[5m]))
)
```

**시각화**:
- **타입**: Time series (Graph)
- **Y축**: Seconds
- **범례**: `{{token_status}}` - P95

**설명**: 유효한 토큰 vs 무효한 토큰 처리 시간 비교

---

### 패널 10: 종합 대시보드 요약

**제목**: 보안 및 성능 요약

**쿼리**:
```promql
# Rate limit 차단률
(sum(rate(photo_api_rate_limit_hits_total[5m])) 
/ 
sum(rate(photo_api_rate_limit_requests_total[5m]))) * 100

# 브루트포스 시도율
sum(rate(photo_api_share_link_brute_force_attempts_total[5m])) 
/ 
sum(rate(photo_api_share_link_access_total[5m])) * 100

# 이미지 접근 성공률
sum(rate(photo_api_image_access_total{result="success"}[5m])) 
/ 
sum(rate(photo_api_image_access_total[5m])) * 100
```

**시각화**:
- **타입**: Stat (단일 통계)
- **모드**: Big number
- **임계값**:
  - Rate limit 차단률 > 10%: 경고 (노란색)
  - Rate limit 차단률 > 20%: 위험 (빨간색)
  - 브루트포스 시도율 > 5%: 경고
  - 이미지 접근 성공률 < 90%: 경고

---

## 알림 규칙 (Alertmanager)

### 1. Rate Limiting 과도한 차단

```yaml
- alert: HighRateLimitHits
  expr: rate(photo_api_rate_limit_hits_total[5m]) * 60 > 100
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Rate limit 차단 횟수가 높습니다"
    description: "{{$labels.endpoint}}에서 분당 {{$value}}회 차단 발생"
```

### 2. 브루트포스 공격 탐지

```yaml
- alert: BruteForceAttack
  expr: rate(photo_api_share_link_brute_force_attempts_total[5m]) * 60 > 100
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "브루트포스 공격 탐지"
    description: "{{$labels.client_id}}에서 분당 {{$value}}회 무효한 토큰 시도"
```

### 3. 이미지 접근 성능 저하

```yaml
- alert: SlowImageAccess
  expr: histogram_quantile(0.95, rate(photo_api_image_access_duration_seconds_bucket[5m])) > 2
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "이미지 접근 응답 시간이 느립니다"
    description: "P95 응답 시간: {{$value}}초"
```

### 4. 공유 링크 접근 실패율 증가

```yaml
- alert: HighShareLinkFailureRate
  expr: |
    (sum(rate(photo_api_share_link_access_total{result="denied"}[5m]))
     / 
     sum(rate(photo_api_share_link_access_total[5m]))) * 100 > 30
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "공유 링크 접근 실패율이 높습니다"
    description: "실패율: {{$value}}%"
```

---

## Grafana 대시보드 JSON

전체 대시보드 JSON 파일은 `grafana/dashboard-photo-api-security.json`에 저장되어 있습니다.

**대시보드 특징**:
- **리프레시 간격**: 30초
- **시간 범위**: 최근 1시간 (기본)
- **변수**: 
  - `instance`: 인스턴스 선택
  - `endpoint`: 엔드포인트 필터링

**패널 구성**:
1. Rate Limiting 개요 (2개 패널)
2. 공유 링크 접근 패턴 (3개 패널)
3. 브루트포스 공격 탐지 (1개 패널)
4. 이미지 접근 패턴 (2개 패널)
5. 성능 모니터링 (2개 패널)

---

## 모니터링 체크리스트

### 일일 확인 사항
- [ ] Rate limit 차단 횟수 확인
- [ ] 브루트포스 공격 시도 확인
- [ ] 이미지 접근 성공률 확인
- [ ] 응답 시간 이상 확인

### 주간 확인 사항
- [ ] Rate limit 설정 최적화 (차단률이 너무 높거나 낮으면 조정)
- [ ] 공유 링크 접근 패턴 분석
- [ ] 의심스러운 IP 활동 검토
- [ ] 성능 트렌드 분석

### 월간 확인 사항
- [ ] 메트릭 수집 정확성 검증
- [ ] 알림 규칙 최적화
- [ ] 대시보드 개선
- [ ] 보안 이벤트 리뷰

---

## 참고 자료

- [Prometheus 쿼리 가이드](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana 대시보드 가이드](https://grafana.com/docs/grafana/latest/dashboards/)
- [Alertmanager 설정 가이드](https://prometheus.io/docs/alerting/latest/alertmanager/)
<<<<<<< HEAD

=======
>>>>>>> e5275842b063860b231ec5810202b146e5fc1f54
