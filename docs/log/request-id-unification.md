# request_id 통일 (nginx-proxy ↔ photo-api)

## 규칙

| 구분 | 값 |
|------|-----|
| **HTTP 헤더** | `X-Request-ID` |
| **로그 필드명** | `request_id` (JSON) |

- **nginx-proxy**: 요청마다 `$request_id` 생성 후 `X-Request-ID`로 백엔드에 전달. access 로그 JSON에 `request_id` 출력.
- **photo-api**: `X-Request-ID`를 읽어 없으면 자체 생성 후, 모든 요청 로그에 `request_id`로 출력. 응답 헤더에도 `X-Request-ID` 설정.

이렇게 하면 Loki/Grafana에서 같은 요청에 대한 nginx 로그와 API 로그를 `request_id`로 연관해 조회할 수 있다.

## 참고

- nginx 설정: `nginx-proxy/conf/nginx-proxy.conf` (log_format `metrics_json`, `proxy_set_header X-Request-ID`)
- API 미들웨어: `app/middlewares/logging_middleware.py` (`REQUEST_ID_HEADER = "X-Request-ID"`)
