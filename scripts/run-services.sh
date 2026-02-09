#!/bin/bash
# photo-api, promtail 시작 (실행 중이면 재시작)
# 메트릭은 앱 /metrics 엔드포인트로 Prometheus가 스크래핑
# 사용법: sudo ./scripts/run-services.sh

set -e

SERVICES="photo-api promtail"

for svc in $SERVICES; do
  systemctl restart "$svc"
  echo "  $svc: $(systemctl is-active "$svc")"
done

SCRIPT_DIR="/home/ubuntu/photo-api/scripts"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="/opt/photo-api/.env"

# 환경변수 로드: 현재 디렉토리 .env → /opt/photo-api/.env 순서
if [[ -z "${LOKI_URL:-}" ]]; then
  if [[ -f "$PROJECT_ROOT/.env" ]]; then
    echo "환경변수 로드: $PROJECT_ROOT/.env"
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
  elif [[ -f "$ENV_FILE" ]]; then
    echo "환경변수 로드: $ENV_FILE"
    set -a
    source "$ENV_FILE"
    set +a
  fi
fi

# 필수 환경변수 검증
missing=()
[[ -z "${LOKI_URL:-}" ]] && missing+=("LOKI_URL")

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "오류: 필수 환경변수가 설정되지 않았습니다: ${missing[*]}" >&2
  echo "사용법: .env 파일을 생성하세요" >&2
  exit 1
fi

# INSTANCE_IP 자동 감지
INSTANCE_IP="${INSTANCE_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"

cd "$SCRIPT_DIR"
chmod +x 1-install-python.sh 2-setup-photo-api.sh 3-setup-promtail.sh run-services.sh 2>/dev/null || true

echo "=== 2/3 photo-api systemd 패키징 ==="
bash "$SCRIPT_DIR/2-setup-photo-api.sh"

# .env 파일을 /opt/photo-api/.env로 복사 (없으면 생성)
echo "=== .env 파일 설정 ==="
mkdir -p /opt/photo-api
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  cp "$PROJECT_ROOT/.env" "$ENV_FILE"
  echo "  복사: $PROJECT_ROOT/.env → $ENV_FILE"
else
  cat > "$ENV_FILE" << EOF
# photo-api, promtail 환경변수 (메트릭은 Prometheus가 /metrics 스크래핑)
LOKI_URL=$LOKI_URL
INSTANCE_IP=$INSTANCE_IP
EOF
  echo "  생성: $ENV_FILE"
fi
chmod 600 "$ENV_FILE"

echo "=== 3/3 Promtail 설치 및 구성 ==="
bash "$SCRIPT_DIR/3-setup-promtail.sh"

echo "=== 이미지 빌드 스크립트 완료 ==="
echo "서비스 시작: systemctl start photo-api promtail"
echo "환경변수 변경: $ENV_FILE 수정 후 systemctl restart photo-api promtail"