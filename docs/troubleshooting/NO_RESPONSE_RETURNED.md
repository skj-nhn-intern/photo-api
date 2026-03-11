# RuntimeError: No response returned. (POST /auth/login)

## 현상

- **경로**: `POST /auth/login`
- **에러**: `RuntimeError: No response returned.`
- **HTTP 상태**: 500
- **클라이언트**: `Python/3.12 aiohttp/3.9.1`
- **발생 위치**: Starlette `BaseHTTPMiddleware`의 `call_next()` 내부

## 발생 원인

이 에러는 **라우트가 응답을 반환하지 않았다**는 뜻이 아니라, **클라이언트가 응답을 받기 전에 연결을 끊었을 때** Starlette 미들웨어 체인에서 발생하는 것으로 알려져 있습니다.

### 1. 클라이언트 연결 종료 (가장 유력)

- 클라이언트가 **타임아웃**으로 연결을 끊거나, **요청 취소**를 보냄.
- `user_agent`가 `aiohttp`이므로, 스크립트/봇에서 **짧은 타임아웃** 또는 **응답 대기 없이 종료**했을 가능성이 큼.
- 서버는 아직 응답을 보내기 전에 클라이언트가 끊어서, 미들웨어 쪽에서 "응답이 한 번도 전송되지 않았다"고 판단하고 `RuntimeError("No response returned.")`를 발생시킴.

### 2. BaseHTTPMiddleware 동작 방식

- Starlette 이슈/문서에 따르면, `BaseHTTPMiddleware`는 내부적으로 스트림으로 응답을 주고받음.
- 클라이언트가 먼저 연결을 끊으면:
  - `recv_stream.receive()` 등에서 `EndOfStream`(또는 유사)이 발생하고,
  - 응답이 한 번도 `send`되지 않은 상태로 처리 종료되며,
  - 그 결과 `call_next()` 안에서 `RuntimeError("No response returned.")`가 발생함.

### 3. 로드밸런서/프록시 keep-alive·타임아웃 불일치 (가능성 있음)

- **Uvicorn keep-alive가 너무 짧은 경우**  
  - 현재 기본값: `UVICORN_TIMEOUT_KEEP_ALIVE=5` (5초).  
  - Nginx 등 LB가 **백엔드 연결 풀(keepalive)** 을 쓰면, Nginx는 연결을 재사용하는데 **Uvicorn은 5초 동안 유휴인 연결을 끊음**.  
  - LB가 이미 끊긴(또는 반쯤 끊긴) 연결로 요청을 보내면, 백엔드에서 응답을 제대로 보내지 못하고 "No response returned"가 날 수 있음.
- **LB → 백엔드 타임아웃**  
  - LB의 `proxy_read_timeout` 등이 짧으면, 백엔드가 응답하기 전에 LB가 연결을 끊을 수 있음.  
  - 그러면 백엔드 입장에서는 “클라이언트(LB)가 먼저 끊음”과 동일한 상황이 되어 같은 에러가 발생할 수 있음.
- **클라이언트 → LB 구간**  
  - 클라이언트와 LB 사이의 idle/read 타임아웃이 짧아도, LB가 먼저 끊으면 최종적으로 백엔드에 “연결 끊김”으로 전달될 수 있음.

## 해결 방안

### 1. 클라이언트 측 (우선 적용 권장)

- **타임아웃 증가**  
  - 로그인은 DB/인증 처리로 수 초 걸릴 수 있으므로, `aiohttp` 등에서 **읽기/연결 타임아웃을 충분히** 두기 (예: 10~30초).
- **응답을 반드시 대기**  
  - 요청을 보낸 뒤 **`response.read()` 또는 `response.json()` 등으로 응답을 끝까지 읽은 후** 연결이 닫히도록 코드 작성.
- **재시도**  
  - 네트워크/타임아웃으로 실패할 수 있으므로, 짧은 백오프로 1~2회 재시도하는 것도 도움이 됨.

예시 (aiohttp):

```python
# 타임아웃을 충분히 (예: 30초)
timeout = aiohttp.ClientTimeout(total=30, connect=10)
async with aiohttp.ClientSession(timeout=timeout) as session:
    async with session.post(
        "https://your-api/auth/login",
        json={"email": "...", "password": "..."},
    ) as resp:
        # 반드시 응답 본문을 읽어서 연결이 정상 종료되도록 함
        data = await resp.json()
```

### 2. 서버 측

- **Uvicorn keep-alive를 LB와 맞추기 (권장)**  
  - Nginx `proxy_read_timeout`이 60초라면, **Uvicorn keep-alive를 그보다 짧지 않게** 두는 것이 안전함.  
  - 예: `UVICORN_TIMEOUT_KEEP_ALIVE=60` (또는 최소 30).  
  - LB가 keepalive로 백엔드 연결을 재사용할 때, Uvicorn이 그 전에 유휴 연결을 끊어서 “끊긴 연결 재사용”이 되지 않도록 함.  
  - 설정: `conf/env.example`, `scripts/2-setup-photo-api.sh` 및 배포 스크립트에서 `UVICORN_TIMEOUT_KEEP_ALIVE` 조정.  
  - 자세한 내용은 `docs/CONNECTION_PERFORMANCE.md` 참고.
- **LB( Nginx ) 타임아웃 확인**  
  - `proxy_connect_timeout`, `proxy_send_timeout`, `proxy_read_timeout`이 충분한지 확인 (예: 60초).  
  - 로그인처럼 DB/인증이 걸리는 구간은 짧은 타임아웃이면 LB가 먼저 끊을 수 있음.
- **해당 RuntimeError를 500이 아닌 "클라이언트 끊김"으로 처리**  
  - 이 예외를 잡아서 **499 Client Closed Request** 등으로 응답하고, 로그/메트릭에서 500과 구분 (이미 `app/main.py`에서 처리됨).
- **Starlette/uvicorn 업그레이드**  
  - "No response returned" 관련 패치가 포함된 Starlette 버전이 있다면 업그레이드하여 빈도가 줄어드는지 확인.
- **느린 로그인 개선**  
  - DB/외부 호출이 느리면 타임아웃 전에 응답이 나가도록 인덱스, 쿼리, 캐시 등을 점검.

## 요약

| 구분 | 내용 |
|------|------|
| **원인** | (1) 클라이언트가 응답 전에 연결을 끊거나 요청 취소. (2) **로드밸런서 keep-alive·타임아웃 불일치** (Uvicorn 5초 keep-alive vs Nginx 60초 등)로 끊긴/반쯤 끊긴 연결 재사용 시에도 발생할 수 있음. Starlette `BaseHTTPMiddleware`가 "한 번도 응답이 전송되지 않음"을 감지해 `RuntimeError("No response returned.")` 발생. |
| **클라이언트** | aiohttp 등에서 타임아웃을 넉넉히 하고, 응답 본문을 끝까지 읽은 뒤 연결을 닫도록 수정. |
| **서버** | **`UVICORN_TIMEOUT_KEEP_ALIVE`를 LB 타임아웃에 맞춰 증가** (예: 60초). 해당 `RuntimeError`는 499로 처리해 5xx와 구분. |
