# 안정성 개선 흐름도

이 문서는 STABILITY_AUDIT.md와 SECURITY_AUDIT.md에 기반한 안정성 개선 사항의 구현 흐름을 Mermaid 다이어그램으로 설명합니다.

## 1. Circuit Breaker 상태 전이 흐름

```mermaid
stateDiagram-v2
    [*] --> CLOSED: 초기 상태
    
    CLOSED --> CLOSED: 성공 (카운터 리셋)
    CLOSED --> OPEN: 실패 누적 (threshold 초과)
    
    OPEN --> OPEN: 요청 차단
    OPEN --> HALF_OPEN: Timeout 경과 (테스트 모드)
    
    HALF_OPEN --> CLOSED: 성공 (success_threshold 달성)
    HALF_OPEN --> OPEN: 실패
    
    CLOSED --> [*]
    OPEN --> [*]
    HALF_OPEN --> [*]
    
    note right of CLOSED
        정상 동작 상태
        모든 요청 허용
    end note
    
    note right of OPEN
        차단 상태
        빠른 실패 (fail-fast)
        리소스 보호
    end note
    
    note right of HALF_OPEN
        테스트 모드
        제한된 요청 허용
        복구 시도
    end note
```

## 2. 외부 서비스 호출 흐름 (재시도 + Circuit Breaker)

```mermaid
sequenceDiagram
    participant Client
    participant Service as Service Layer
    participant CB as Circuit Breaker
    participant Retry as Retry Logic
    participant External as External Service
    
    Client->>Service: 요청 (예: 파일 업로드)
    Service->>CB: Circuit Breaker 체크
    
    alt Circuit Breaker 상태: CLOSED
        CB->>Retry: 요청 전달
        Retry->>External: HTTP 요청 (시도 1)
        
        alt 성공
            External-->>Retry: 200 OK
            Retry-->>CB: 성공
            CB->>CB: 실패 카운터 리셋
            CB-->>Service: 결과 반환
            Service-->>Client: 성공 응답
        else 실패 (일시적 오류)
            External-->>Retry: 500/Timeout
            Retry->>Retry: 지수 백오프 대기
            Retry->>External: HTTP 요청 (시도 2)
            
            alt 재시도 성공
                External-->>Retry: 200 OK
                Retry-->>CB: 성공
                CB-->>Service: 결과 반환
                Service-->>Client: 성공 응답
            else 재시도 실패
                External-->>Retry: 500/Timeout
                Retry->>Retry: 지수 백오프 대기
                Retry->>External: HTTP 요청 (시도 3)
                
                alt 최종 재시도 성공
                    External-->>Retry: 200 OK
                    Retry-->>CB: 성공
                    CB-->>Service: 결과 반환
                    Service-->>Client: 성공 응답
                else 최종 실패
                    External-->>Retry: 500/Timeout
                    Retry-->>CB: 실패
                    CB->>CB: 실패 카운터 증가
                    CB->>CB: OPEN 상태로 전이 (threshold 초과 시)
                    CB-->>Service: 예외 발생
                    Service-->>Client: 에러 응답
                end
            end
        end
    else Circuit Breaker 상태: OPEN
        CB-->>Service: Circuit Breaker OPEN 예외
        Service-->>Client: 빠른 실패 (503 Service Unavailable)
    else Circuit Breaker 상태: HALF_OPEN
        CB->>Retry: 제한된 요청 허용
        Retry->>External: HTTP 요청 (테스트)
        
        alt 테스트 성공
            External-->>Retry: 200 OK
            Retry-->>CB: 성공
            CB->>CB: 성공 카운터 증가
            CB->>CB: CLOSED 상태로 전이 (threshold 달성 시)
            CB-->>Service: 결과 반환
            Service-->>Client: 성공 응답
        else 테스트 실패
            External-->>Retry: 500/Timeout
            Retry-->>CB: 실패
            CB->>CB: OPEN 상태로 전이
            CB-->>Service: 예외 발생
            Service-->>Client: 에러 응답
        end
    end
```

## 3. Graceful Shutdown 흐름 (Autoscaling 환경)

```mermaid
sequenceDiagram
    participant LB as Load Balancer
    participant App as Application
    participant Health as Health Check
    participant Request as In-Flight Requests
    participant BG as Background Tasks
    participant DB as Database
    
    Note over LB,DB: 정상 동작
    LB->>Health: GET /health (30초마다)
    Health->>DB: SELECT 1 (타임아웃 2초)
    DB-->>Health: 성공
    Health-->>LB: 200 OK
    LB->>App: 트래픽 전송
    
    Note over LB,DB: Shutdown 시작
    LB->>App: SIGTERM 전송 (Autoscaling 그룹)
    App->>Health: ready.set(0)
    Health->>Health: 상태 변경 (unhealthy)
    
    Note over LB,DB: 새 요청 차단
    LB->>Health: GET /health
    Health-->>LB: 503 Service Unavailable
    LB->>LB: 새 요청 차단 (트래픽 라우팅 중지)
    
    Note over LB,DB: 진행 중인 요청 완료 대기
    App->>Request: 진행 중인 요청 확인
    alt 진행 중인 요청 있음
        Request-->>App: in_flight_requests > 0
        App->>App: 대기 (최대 30초)
        loop 최대 30초 동안
            App->>Request: 요청 완료 확인
            alt 요청 완료
                Request-->>App: in_flight_requests = 0
            else 타임아웃
                App->>App: 강제 종료
            end
        end
    else 진행 중인 요청 없음
        Request-->>App: in_flight_requests = 0
    end
    
    Note over LB,DB: 백그라운드 작업 종료
    App->>BG: Pushgateway 작업 취소
    BG-->>App: 취소 완료
    App->>BG: 로그 서비스 종료
    BG-->>App: 로그 플러시 완료
    
    Note over LB,DB: 리소스 정리
    App->>DB: DB 연결 종료
    DB-->>App: 연결 종료 완료
    App->>App: 프로세스 종료
```

## 4. CDN 토큰 캐시 LRU 흐름

```mermaid
flowchart TD
    Start([토큰 요청]) --> CheckCache{캐시 확인}
    
    CheckCache -->|캐시 Hit| CheckExpiry{만료 확인}
    CheckExpiry -->|유효| UseCache[캐시 토큰 사용<br/>LRU: move_to_end]
    CheckExpiry -->|만료| RemoveCache[캐시 제거]
    
    CheckCache -->|캐시 Miss| CheckSize{캐시 크기 확인}
    RemoveCache --> CheckSize
    
    CheckSize -->|크기 초과| EvictOldest[가장 오래된 항목 제거<br/>popitem last=False]
    CheckSize -->|크기 OK| RequestToken[CDN API 호출<br/>Circuit Breaker + Retry]
    EvictOldest --> RequestToken
    
    RequestToken --> Success{성공?}
    Success -->|성공| CacheToken[캐시에 저장<br/>move_to_end]
    Success -->|실패| ReturnNone[None 반환<br/>백엔드 스트리밍]
    
    CacheToken --> ReturnToken[토큰 반환]
    UseCache --> ReturnToken
    
    ReturnToken --> End([완료])
    ReturnNone --> End
    
    style CheckCache fill:#e1f5ff
    style CheckExpiry fill:#e1f5ff
    style CheckSize fill:#fff4e1
    style RequestToken fill:#ffe1e1
    style CacheToken fill:#e1ffe1
```

## 5. 전체 안정성 개선 아키텍처

```mermaid
graph TB
    subgraph "Client Layer"
        Client[클라이언트]
    end
    
    subgraph "Application Layer"
        Router[FastAPI Router]
        Service[Service Layer]
    end
    
    subgraph "Resilience Layer"
        CB[Circuit Breaker<br/>상태: CLOSED/OPEN/HALF_OPEN]
        Retry[Retry Logic<br/>지수 백오프]
        Cache[LRU Cache<br/>크기 제한: 1000]
    end
    
    subgraph "External Services"
        Storage[NHN Object Storage]
        CDN[NHN CDN]
        Log[NHN Log Service]
    end
    
    subgraph "Monitoring"
        Metrics[Prometheus Metrics]
        Health[Health Check<br/>타임아웃: 2초]
    end
    
    Client -->|HTTP 요청| Router
    Router --> Service
    
    Service -->|외부 서비스 호출| CB
    CB -->|요청 허용| Retry
    CB -->|요청 차단| Service
    
    Retry -->|재시도| Storage
    Retry -->|재시도| CDN
    Retry -->|재시도| Log
    
    Service -->|토큰 조회| Cache
    Cache -->|캐시 Hit| Service
    Cache -->|캐시 Miss| CDN
    
    Storage -->|성공/실패| CB
    CDN -->|성공/실패| CB
    Log -->|성공/실패| CB
    
    CB -->|상태 업데이트| Metrics
    Service -->|메트릭 수집| Metrics
    Health -->|상태 확인| Metrics
    
    style CB fill:#ffcccc
    style Retry fill:#ffffcc
    style Cache fill:#ccffcc
    style Health fill:#ccccff
    style Metrics fill:#ffccff
```

## 6. Health Check 흐름 (Autoscaling 환경)

```mermaid
flowchart TD
    Start([로드밸런서 Health Check]) --> Timeout{타임아웃 설정<br/>2초}
    
    Timeout --> CheckDB[DB 연결 확인<br/>SELECT 1]
    CheckDB --> DBResult{결과}
    
    DBResult -->|성공| CheckStorage[Object Storage<br/>토큰 확인]
    DBResult -->|실패| Unhealthy[503 Unhealthy<br/>DB 에러 반환]
    DBResult -->|타임아웃| Unhealthy
    
    CheckStorage --> StorageResult{결과}
    StorageResult -->|성공/Unknown| Healthy[200 Healthy<br/>인스턴스 정보 포함]
    StorageResult -->|실패| Healthy
    
    Healthy --> End1([로드밸런서<br/>트래픽 전송])
    Unhealthy --> End2([로드밸런서<br/>트래픽 차단])
    
    style Timeout fill:#fff4e1
    style CheckDB fill:#e1f5ff
    style CheckStorage fill:#e1f5ff
    style Healthy fill:#e1ffe1
    style Unhealthy fill:#ffe1e1
```

## 7. 재시도 로직 상세 흐름

```mermaid
flowchart TD
    Start([함수 호출]) --> Attempt1[시도 1]
    
    Attempt1 --> Result1{결과}
    Result1 -->|성공| Success[성공 반환]
    Result1 -->|실패| CheckRetry1{재시도 가능?}
    
    CheckRetry1 -->|아니오| Fail[최종 실패]
    CheckRetry1 -->|예| Wait1[대기: 1초<br/>지수 백오프]
    
    Wait1 --> Attempt2[시도 2]
    Attempt2 --> Result2{결과}
    Result2 -->|성공| Success
    Result2 -->|실패| CheckRetry2{재시도 가능?}
    
    CheckRetry2 -->|아니오| Fail
    CheckRetry2 -->|예| Wait2[대기: 2초<br/>지수 백오프]
    
    Wait2 --> Attempt3[시도 3]
    Attempt3 --> Result3{결과}
    Result3 -->|성공| Success
    Result3 -->|실패| Fail
    
    Success --> End1([완료])
    Fail --> End2([예외 발생])
    
    style Attempt1 fill:#e1f5ff
    style Attempt2 fill:#fff4e1
    style Attempt3 fill:#ffe1e1
    style Success fill:#e1ffe1
    style Fail fill:#ffcccc
```

## 8. 메트릭 수집 흐름

```mermaid
sequenceDiagram
    participant App as Application
    participant CB as Circuit Breaker
    participant Retry as Retry Logic
    participant Metrics as Prometheus
    participant Gateway as Pushgateway
    
    App->>CB: 외부 서비스 호출
    CB->>CB: 상태 변경 감지
    CB->>Metrics: circuit_breaker_state 업데이트
    
    App->>Retry: 재시도 실행
    Retry->>Metrics: retry_attempts_total 증가
    
    App->>Metrics: external_request_errors_total 증가
    App->>Metrics: external_request_duration_seconds 기록
    
    Note over Metrics,Gateway: 주기적 푸시 (설정 시)
    Metrics->>Gateway: 메트릭 푸시 (주기적)
    Gateway->>Gateway: 메트릭 저장
    
    Note over Metrics,Gateway: Prometheus 스크래핑
    Metrics->>Metrics: /metrics 엔드포인트 노출
```

## 요약

### 구현된 개선 사항

1. **Circuit Breaker**: 외부 서비스 장애 시 빠른 실패로 리소스 보호
2. **재시도 로직**: 일시적 오류에 대한 지수 백오프 재시도
3. **CDN 캐시 LRU**: 메모리 사용량 제한 및 성능 최적화
4. **Graceful Shutdown**: Autoscaling 환경에서 안전한 종료
5. **Health Check 최적화**: 빠른 응답 시간 (2초 타임아웃)
6. **메트릭 수집**: Circuit Breaker 상태 및 재시도 추적

### 주요 흐름

- **외부 서비스 호출**: Circuit Breaker → Retry → External Service
- **Graceful Shutdown**: SIGTERM → Health Check 실패 → 요청 완료 대기 → 리소스 정리
- **캐시 관리**: LRU 알고리즘으로 메모리 사용량 제한
- **모니터링**: Prometheus 메트릭으로 실시간 상태 추적

이러한 개선 사항들을 통해 애플리케이션의 안정성과 가용성이 크게 향상되었습니다.
