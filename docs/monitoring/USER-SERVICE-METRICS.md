# 사용자 서비스 메트릭 시각화 가이드

로그인 성공률, JWT 토큰 발급/접근 성공률, 신규 가입자 추이를 Grafana에서 보기 위한 PromQL과 패널 설정입니다.

**사용 메트릭** (앱에서 수집):
- `photo_api_user_login_total` — 라벨: `result` (success | failure)
- `photo_api_user_registration_total` — 라벨: `result` (success | failure)
- `photo_api_jwt_token_validation_total` — 라벨: `result` (success | failure) — Bearer JWT 검증 시도(보호된 라우트 접근 시)

---

## 1. 로그인 성공률 (%)

**의미**: 로그인 시도 대비 성공 비율.

**PromQL**
```promql
sum(rate(photo_api_user_login_total{result="success"}[5m])) 
/ 
sum(rate(photo_api_user_login_total[5m])) * 100
```

**Grafana 패널**
| 항목 | 값 |
|------|-----|
| 시각화 | Stat 또는 Time series |
| Unit | `percent (0-100)` |
| Threshold | 예: 95 이상 녹색, 80 미만 경고, 50 미만 위험 |
| 설명 | 5분 구간 로그인 성공률 |

---

## 2. JWT 토큰 발급 성공률 (%)

**의미**: 로그인 시도 대비 JWT 발급 성공 비율. (로그인 성공 = JWT 1개 발급)

**PromQL**
```promql
sum(rate(photo_api_user_login_total{result="success"}[5m])) 
/ 
sum(rate(photo_api_user_login_total[5m])) * 100
```

**Grafana 패널**
| 항목 | 값 |
|------|-----|
| 시각화 | Stat 또는 Time series |
| Unit | `percent (0-100)` |
| 설명 | 5분 구간 JWT 발급 성공률 (= 로그인 성공률) |

---

## 3. JWT 토큰 접근(검증) 성공률 (%)

**의미**: 보호된 API 접근 시 Bearer JWT 검증 시도 대비 성공 비율.

**PromQL**
```promql
sum(rate(photo_api_jwt_token_validation_total{result="success"}[5m])) 
/ 
sum(rate(photo_api_jwt_token_validation_total[5m])) * 100
```

**Grafana 패널**
| 항목 | 값 |
|------|-----|
| 시각화 | Stat 또는 Time series |
| Unit | `percent (0-100)` |
| 설명 | 5분 구간 JWT 검증 성공률 (실패 = 토큰 없음/만료/유효하지 않음/유저 없음) |

---

## 4. JWT 토큰 발급율 (건수)

**의미**: 로그인 성공 시 JWT 1개 발급이므로, 로그인 성공 건수 = JWT 발급 건수.

**PromQL**
```promql
# 초당 JWT 발급 수
sum(rate(photo_api_user_login_total{result="success"}[5m]))

# 분당 JWT 발급 수 (추천)
sum(rate(photo_api_user_login_total{result="success"}[5m])) * 60
```

**Grafana 패널**
| 항목 | 값 |
|------|-----|
| 시각화 | Time series 또는 Stat |
| Unit | 분당이면 `reqm` (건/분), 초당이면 `1/s` |
| Legend | `JWT 발급 (분당)` 등 |

---

## 5. 신규 가입자 추이

**의미**: 회원가입 성공 건수 시계열.

**PromQL**
```promql
# 분당 신규 가입자
sum(rate(photo_api_user_registration_total{result="success"}[5m])) * 60

# 1시간 구간 신규 가입자 (increase)
sum(increase(photo_api_user_registration_total{result="success"}[1h]))
```

**Grafana 패널**
| 항목 | 값 |
|------|-----|
| 시각화 | Time series (추이), Stat (현재/구간 합계) |
| Unit | `reqm` (건/분) 또는 `short` (건) |
| Legend | `신규 가입 (분당)` 등 |

---

## 6. 한 화면에 넣을 때 예시

| 패널 | PromQL | 시각화 | Unit |
|------|--------|--------|------|
| 로그인 성공률 | `sum(rate(photo_api_user_login_total{result="success"}[5m])) / sum(rate(photo_api_user_login_total[5m])) * 100` | Stat | percent (0-100) |
| JWT 발급 성공률 | 위와 동일 (로그인 성공률) | Stat | percent (0-100) |
| JWT 접근(검증) 성공률 | `sum(rate(photo_api_jwt_token_validation_total{result="success"}[5m])) / sum(rate(photo_api_jwt_token_validation_total[5m])) * 100` | Stat | percent (0-100) |
| JWT 발급 (분당) | `sum(rate(photo_api_user_login_total{result="success"}[5m])) * 60` | Time series | reqm |
| 신규 가입 (분당) | `sum(rate(photo_api_user_registration_total{result="success"}[5m])) * 60` | Time series | reqm |
| JWT 검증 성공률 추이 | JWT 접근 성공률 쿼리와 동일 | Time series | percent (0-100) |

---

## 7. 보조 지표 (선택)

**회원가입 성공률**
```promql
sum(rate(photo_api_user_registration_total{result="success"}[5m])) 
/ 
sum(rate(photo_api_user_registration_total[5m])) * 100
```

**로그인 시도 수 (분당)**
```promql
sum(rate(photo_api_user_login_total[5m])) * 60
```
