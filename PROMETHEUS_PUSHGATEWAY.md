# Prometheus Pushgateway 연동

Photo API는 메트릭을 **스크래핑**과 **Pushgateway** 두 방식으로 제공합니다.

## 방식 요약

| 방식 | 설명 | 사용 시점 |
|------|------|-----------|
| **스크래핑** | Prometheus가 `http://인스턴스:8000/metrics` 를 주기적으로 조회 | 기본. 인스턴스가 Prometheus에서 직접 접근 가능할 때 |
| **Pushgateway** | 앱이 주기적으로 Pushgateway로 메트릭 전송, Prometheus는 Pushgateway만 스크래핑 | 인스턴스가 단기 생명이거나, 방화벽/사설망으로 직접 스크래핑이 어려울 때 |

## Pushgateway 사용 시 설정

### 1. 환경 변수

Pushgateway 인스턴스를 쓰려면 다음만 설정하면 됩니다.

```bash
# Pushgateway URL (설정 시 주기 푸시 활성화)
PROMETHEUS_PUSHGATEWAY_URL="http://pushgateway:9091"

# 전송 주기(초). 기본 30초
PROMETHEUS_PUSH_INTERVAL_SECONDS=30
```

- `PROMETHEUS_PUSHGATEWAY_URL` 을 **비우면** Pushgateway 푸시는 하지 않고, `/metrics` 스크래핑만 사용합니다.
- 주기는 최소 15초로 제한됩니다.

### 2. 동작

- 앱 기동 시 `PROMETHEUS_PUSHGATEWAY_URL` 이 있으면 백그라운드에서 **주기적으로** 다음을 Pushgateway로 푸시합니다.
  - **앱 메트릭**: job=`photo-api`, instance=INSTANCE_IP
  - **node_exporter**: 같은 주기로 `127.0.0.1:9100/metrics` 를 읽어 job=`node_exporter`, instance=INSTANCE_IP 로 푸시 (동일 인스턴스에 node_exporter가 떠 있을 때)
- Prometheus는 **Pushgateway만 스크래핑**하면 앱 메트릭과 호스트(CPU/메모리 등) 메트릭을 함께 수집할 수 있습니다.

### 3. Prometheus 설정 예시

Pushgateway를 스크래핑하도록 설정합니다.

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'pushgateway'
    honor_labels: true
    static_configs:
      - targets: ['pushgateway:9091']
```

- `honor_labels: true` 로 Pushgateway에 붙은 job/instance 라벨을 그대로 사용하는 것을 권장합니다.

## 아키텍처 예시

```
[Photo API 인스턴스들]
  │ /metrics (스크래핑용, 항상 노출)
  │ 주기적으로 push (PROMETHEUS_PUSHGATEWAY_URL 설정 시)
  ▼
[Pushgateway]
  │
  ▼
[Prometheus]
  │ 스크래핑: Pushgateway 또는 직접 Photo API /metrics
  ▼
[Grafana 등]
```

## 추후 연동 시 체크리스트

- [ ] Pushgateway 인스턴스 배포 (예: Docker/ Kubernetes)
- [ ] Photo API 환경 변수에 `PROMETHEUS_PUSHGATEWAY_URL` 설정
- [ ] Prometheus에 Pushgateway target 추가
- [ ] 필요 시 `PROMETHEUS_PUSH_INTERVAL_SECONDS` 조정 (기본 30초)
- [ ] 로그에서 `Pushgateway enabled: url=...` 로 기동 시 푸시 활성화 확인

## 참고

- [Prometheus Pushgateway](https://prometheus.io/docs/practices/pushing/)
- [prometheus_client push_to_gateway](https://github.com/prometheus/client_python#pushgateway)
