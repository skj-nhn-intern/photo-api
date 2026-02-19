# 로그 수집·모니터링 문서

이 폴더는 Photo API 로그 수집(Promtail), 라벨 정책, 서비스 모니터링용 로그 정의를 정리한 문서를 둡니다.

| 문서 | 설명 |
|------|------|
| [2026-02-17-promtail-labels-and-service-monitoring-logs.md](./2026-02-17-promtail-labels-and-service-monitoring-logs.md) | Promtail 라벨 추가(event, level, path_prefix), 서비스 모니터링용 로그 구체화, 추가 메트릭 제안 |
| [request-id-unification.md](./request-id-unification.md) | nginx-proxy와 request_id 통일 (X-Request-ID 헤더, request_id 로그 필드) |
| [event-granularity.md](./event-granularity.md) | 공유·사진·스토리지·CDN 이벤트 세분화, 재시도 retry_target |

- **Promtail 설정**: 저장소 루트 `conf/promtail-config.yaml`
- **대시보드·쿼리**: `docs/monitoring/DASHBOARD-LAYOUT-SLO-SERVICE.md`
