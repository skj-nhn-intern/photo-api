# 이미지 보안 종합 검토

## 전반적인 보안 평가

### ✅ 강점 (잘 구현된 부분)

#### 1. 일반 이미지 접근 보안
- **JWT 필수**: `Authorization: Bearer {JWT}` 없으면 401 Unauthorized
- **소유자 확인**: 소유자가 아니면 404 Not Found
- **OBS URL 미반환**: API 응답에 OBS URL 절대 포함 안 함
- **CDN Auth Token**: 토큰 없이는 CDN이 접근 거부
- **링크만으로 접근 불가**: 완벽하게 차단됨 ✅

#### 2. 공유 링크 보안
- **토큰 생성**: `secrets.token_urlsafe(32)` 사용 (약 192비트 엔트로피)
- **토큰 고유성**: DB unique constraint로 중복 방지
- **토큰 검증**: DB 조회 + `is_valid` 체크 (만료, 비활성화 확인)
- **앨범 소속 확인**: `get_photo_in_album`으로 해당 앨범 사진만 접근 가능
- **CDN Auth Token**: 공유 링크 이미지도 동일한 CDN Auth Token 사용

#### 3. CDN 보안
- **Auth Token 유효기간**: 기본 120초 (짧은 유효기간)
- **토큰 캐시**: 재사용 가능하지만 짧은 유효기간으로 완화
- **OBS URL 미반환**: 절대 반환하지 않음
- **토큰 없이 접근 불가**: CDN이 자동으로 거부

#### 4. 데이터베이스 보안
- **외래키 제약**: `ondelete="CASCADE"`로 무결성 보장
- **인덱스**: 토큰에 인덱스로 빠른 조회
- **고유 제약**: 토큰 중복 방지

## ⚠️ 개선 권장 사항

### 1. Rate Limiting (중요도: 높음) ✅ 구현 완료

**현재 상태**: Rate limiting이 구현됨

**구현 내용**:
- `slowapi`를 사용한 Rate limiting 미들웨어 구현
- 공유 링크 엔드포인트: IP당 분당 10회 (설정 가능)
- 이미지 접근 엔드포인트: IP당 분당 120회 (설정 가능)
- 일반 엔드포인트: IP당 분당 60회 (설정 가능)
- Rate limit 초과 시 Prometheus 메트릭 수집 및 로깅

**구현 파일**:
- `app/middlewares/rate_limit_middleware.py`: Rate limiting 미들웨어
- `app/config.py`: Rate limiting 설정 (환경 변수)
- `app/routers/share.py`: 공유 링크 엔드포인트에 적용
- `app/routers/photos.py`: 이미지 접근 엔드포인트에 적용

**모니터링**:
- `photo_api_rate_limit_hits_total`: Rate limit 차단 횟수
- `photo_api_rate_limit_requests_total`: Rate limit 체크 요청 수
- Grafana 대시보드에서 실시간 모니터링 가능

### 2. 공유 링크 토큰 길이 (중요도: 낮음)

**현재 상태**: 32자 (URL-safe base64, 약 192비트 엔트로피)

**평가**: 충분히 안전함. 하지만 더 긴 토큰을 사용할 수 있음

**권장 사항** (선택사항):
```python
# 48자로 증가 (약 288비트 엔트로피)
def generate_share_token(length: int = 48) -> str:
    return secrets.token_urlsafe(length)
```

### 3. CDN Auth Token 캐시 (중요도: 낮음)

**현재 상태**: 메모리 캐시 사용, 토큰 재사용 가능

**평가**: 짧은 유효기간(120초)으로 완화되지만, 더 짧은 캐시 TTL 고려 가능

**권장 사항** (선택사항):
```python
# 캐시 TTL을 더 짧게 (30초)
if time.time() < expire_time - 30:  # 1분 → 30초
    return f"https://{self.settings.nhn_cdn_domain}{cdn_path}?token={cached_token}"
```

### 4. 공유 링크 접근 로깅 (중요도: 중간) ✅ 구현 완료

**현재 상태**: 상세한 모니터링 메트릭 수집

**구현 내용**:
- `photo_api_share_link_access_total`: 토큰 상태별 접근 시도 수집
- `photo_api_share_link_brute_force_attempts_total`: 브루트포스 공격 시도 수집
- `photo_api_share_link_access_duration_seconds`: 접근 응답 시간 수집
- `photo_api_share_link_image_access_total`: 이미지 접근 패턴 수집

**모니터링 지표**:
- 무효한 토큰 시도 횟수 (브루트포스 탐지)
- 만료된 토큰 접근 시도
- 특정 IP의 의심스러운 활동
- 이미지 접근 패턴 (앨범 소속 여부)

**시각화**:
- Grafana 대시보드에서 실시간 모니터링
- 브루트포스 공격 자동 탐지 및 알림
- 상세한 접근 패턴 분석 가능

### 5. 공유 링크 토큰 재사용 방지 (중요도: 낮음)

**현재 상태**: 토큰은 재사용 가능 (만료 전까지)

**평가**: 일반적인 사용 패턴에서는 문제 없음. 하지만 일회용 토큰 옵션 고려 가능

**권장 사항** (선택사항):
```python
# ShareLink 모델에 use_once 플래그 추가
use_once: Mapped[bool] = mapped_column(Boolean, default=False)

# 사용 후 비활성화
if share_link.use_once:
    share_link.is_active = False
```

## 보안 시나리오 테스트

### ✅ 시나리오 1: 일반 이미지 - 링크만으로 접근
```
요청: GET /photos/123/image (JWT 없음)
결과: 401 Unauthorized ✅
평가: 완벽하게 차단됨
```

### ✅ 시나리오 2: 일반 이미지 - JWT 있지만 소유자 아님
```
요청: GET /photos/123/image + JWT (다른 사용자)
결과: 404 Not Found ✅
평가: 완벽하게 차단됨
```

### ✅ 시나리오 3: 공유 링크 - 유효한 토큰
```
요청: GET /share/{valid_token}/photos/123/image
결과: 200 OK (CDN Auth Token 포함) ✅
평가: 정상 작동
```

### ✅ 시나리오 4: 공유 링크 - 무효한 토큰
```
요청: GET /share/{invalid_token}/photos/123/image
결과: 404 Not Found ✅
평가: 완벽하게 차단됨
```

### ✅ 시나리오 5: 공유 링크 - 만료된 토큰
```
요청: GET /share/{expired_token}/photos/123/image
결과: 410 Gone ✅
평가: 완벽하게 차단됨
```

### ✅ 시나리오 6: 공유 링크 - 다른 앨범의 사진 접근 시도
```
요청: GET /share/{token}/photos/999/image (다른 앨범의 사진)
결과: 404 Not Found ✅
평가: 완벽하게 차단됨 (get_photo_in_album으로 검증)
```

### ✅ 시나리오 7: OBS URL 직접 접근
```
요청: GET https://object-storage.example.com/container/path/image.jpg
결과: 403 Forbidden (CDN Auth Token 없음) ✅
평가: CDN이 자동으로 거부
```

### ✅ 시나리오 8: 공유 링크 토큰 브루트포스 공격
```
요청: GET /share/{random_token1}/photos/123/image (반복)
요청: GET /share/{random_token2}/photos/123/image (반복)
...
결과: Rate limiting으로 차단 (IP당 분당 10회 제한) ✅
평가: Rate limiting으로 보호됨, 모니터링 메트릭으로 탐지 가능
```

## 보안 체크리스트

### 일반 이미지 보안
- [x] JWT 필수
- [x] 소유자 확인
- [x] OBS URL 미반환
- [x] CDN Auth Token 사용
- [x] 링크만으로 접근 불가

### 공유 링크 보안
- [x] 안전한 토큰 생성 (secrets.token_urlsafe)
- [x] 토큰 고유성 보장 (DB unique constraint)
- [x] 토큰 검증 (DB 조회 + is_valid)
- [x] 앨범 소속 확인
- [x] 만료 시간 확인
- [x] 비활성화 확인
- [x] Rate limiting (구현 완료)
- [x] 브루트포스 공격 탐지 (모니터링 메트릭)

### CDN 보안
- [x] Auth Token 사용
- [x] 짧은 유효기간 (120초)
- [x] OBS URL 미반환
- [x] 토큰 없이 접근 불가

### 데이터베이스 보안
- [x] 외래키 제약
- [x] 인덱스
- [x] 고유 제약

## 종합 평가

### 보안 등급: **A- (우수)**

**강점**:
- 일반 이미지 접근 보안이 매우 강력함
- 공유 링크 보안도 잘 구현됨
- CDN Auth Token 사용으로 OBS 직접 접근 차단
- 토큰 생성 및 검증이 안전함
- Rate limiting 구현 완료
- 상세한 모니터링 메트릭 수집
- 브루트포스 공격 탐지 기능

**개선 완료**:
- ✅ Rate limiting 추가 (브루트포스 공격 방지)
- ✅ 공유 링크 접근 패턴 모니터링 강화

**결론**: 
현재 구현은 **프로덕션 환경에서 사용 가능한 수준**입니다. Rate limiting과 상세한 모니터링이 구현되어 보안이 더욱 강화되었습니다.

## 권장 조치 사항

### 즉시 조치 (필수)
1. ✅ 현재 상태 유지 (이미 잘 구현됨)

### 단기 조치 (완료)
1. ✅ Rate limiting 추가
2. ✅ 공유 링크 접근 패턴 모니터링 강화
3. ✅ Grafana 대시보드 구성
4. ✅ Prometheus 알림 규칙 설정

### 장기 조치 (선택)
1. 공유 링크 토큰 길이 증가 (48자)
2. CDN Auth Token 캐시 TTL 단축 (30초)
3. 일회용 공유 링크 옵션 추가
