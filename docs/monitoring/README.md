# 모니터링 문서

서비스 모니터링 및 대시보드 구성 관련 문서입니다.

## 문서 목록

| 문서 | 설명 |
|------|------|
| [SERVICE-MONITORING-DASHBOARD.md](./SERVICE-MONITORING-DASHBOARD.md) | **서비스 모니터링 대시보드 가이드** — 사용 지표, 수집 방식(메트릭/로그), 시각화 유형(가로·세로축), 수집 이유(운영 관점), SLA 대시보드 만드는 방법 |
| [DASHBOARD-LAYOUT-SLO-SERVICE.md](./DASHBOARD-LAYOUT-SLO-SERVICE.md) | **SLO/SLI Overview 및 서비스별 대시보드** — Overview + Service Monitor(User, Album, Image, Share) Row별 배치·패널·시각화·Nginx 연동 |

**Grafana JSON**: 위 대시보드 구성을 그대로 적용한 JSON은 `grafana/` 폴더에 있습니다.  
- `grafana/dashboard-slo-sli-overview.json` — SLO/SLI Overview  
- `grafana/dashboard-service-user.json` — User (Auth)  
- `grafana/dashboard-service-album.json` — Album  
- `grafana/dashboard-service-image.json` — Image  
- `grafana/dashboard-service-share.json` — Share  
임포트 방법은 `grafana/README.md` 참고.

## 프로젝트 루트 참고 문서

- `HA_MONITORING_METRICS.md` — 고가용성·지표 정의·알림 규칙
- `MONITORING_VISUALIZATION.md` — Grafana 패널·Prometheus 쿼리·SLA 대시보드 구조
- `LOGGING_IMPLEMENTATION_SUMMARY.md` — 구조화 로깅·Loki 연동
