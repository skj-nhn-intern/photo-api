# DB 로그 보기

DB 관련 로그는 **항상** 다음 두 가지가 출력됩니다. 별도 설정 없이 확인할 수 있습니다.

- **느린 쿼리(Slow query)**: 1초 이상 걸린 쿼리 → `event=db`, 메시지 `"Slow query"`, WARNING
- **DB 에러**: 세션/트랜잭션 예외 시 → `event=db`, 메시지 `"DB error"`, ERROR

## 어디서 보나요?

| 출력 대상 | 내용 |
|-----------|------|
| **stdout** | Slow query(WARNING), DB error(ERROR) — 콘솔/ journald |
| **app.log** | 위와 동일 (INFO 이상) |
| **error.log** | DB error(ERROR) 만 |

Loki 등으로 수집했다면:

- DB 이벤트만: `event="db"`
- DB 에러만: `event="db"` + `level="ERROR"` 또는 메시지에 `DB error`
- 느린 쿼리만: 메시지에 `Slow query`

## SQL 문 로그

실행되는 **SQL 문**은 기본적으로 **stdout / app.log**에 출력됩니다 (SQLAlchemy `echo`).

- 끄려면 환경 변수 `DATABASE_ECHO=false`로 설정하면 됩니다.
