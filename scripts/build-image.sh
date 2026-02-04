#!/usr/bin/env bash
# Ubuntu 인스턴스 이미지 빌드: 1~4단계 순차 실행
#
# 사용법:
#   sudo ./scripts/build-image.sh
#   (환경변수는 .env 또는 /opt/photo-api/.env 에서 자동 로드)
#
# 환경변수 변경 시:
#   /opt/photo-api/.env 수정 후 systemctl restart photo-api promtail telegraf
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
[[ -z "${INFLUX_URL:-}" ]] && missing+=("INFLUX_URL")
[[ -z "${INFLUX_TOKEN:-}" ]] && missing+=("INFLUX_TOKEN")
[[ -z "${INFLUX_ORG:-}" ]] && missing+=("INFLUX_ORG")
[[ -z "${INFLUX_BUCKET:-}" ]] && missing+=("INFLUX_BUCKET")

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "오류: 필수 환경변수가 설정되지 않았습니다: ${missing[*]}" >&2
  echo "사용법: .env 파일을 생성하세요" >&2
  exit 1
fi

# INSTANCE_IP 자동 감지
INSTANCE_IP="${INSTANCE_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
INSTANCE_IP="${INSTANCE_IP:-127.0.0.1}"

cd "$SCRIPT_DIR"
chmod +x 1-install-python.sh 2-setup-photo-api.sh 3-setup-promtail.sh 4-setup-telegraf.sh run-services.sh 2>/dev/null || true

echo "=== 1/4 Python 3.11 설치 ==="
bash "$SCRIPT_DIR/1-install-python.sh"

echo "=== 2/4 photo-api systemd 패키징 ==="
bash "$SCRIPT_DIR/2-setup-photo-api.sh"

# .env 파일을 /opt/photo-api/.env로 복사 (없으면 생성)
echo "=== .env 파일 설정 ==="
mkdir -p /opt/photo-api
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  cp "$PROJECT_ROOT/.env" "$ENV_FILE"
  echo "  복사: $PROJECT_ROOT/.env → $ENV_FILE"
else
  cat > "$ENV_FILE" << EOF
# photo-api, promtail, telegraf 환경변수
LOKI_URL=$LOKI_URL
INSTANCE_IP=$INSTANCE_IP
INFLUX_URL=$INFLUX_URL
INFLUX_TOKEN=$INFLUX_TOKEN
INFLUX_ORG=$INFLUX_ORG
INFLUX_BUCKET=$INFLUX_BUCKET
EOF
  echo "  생성: $ENV_FILE"
fi
chmod 600 "$ENV_FILE"

echo "=== 3/4 Promtail 설치 및 구성 ==="
bash "$SCRIPT_DIR/3-setup-promtail.sh"

echo "=== 4/4 Telegraf 설치 및 구성 ==="
bash "$SCRIPT_DIR/4-setup-telegraf.sh"

echo "=== 이미지 빌드 스크립트 완료 ==="
echo "서비스 시작: systemctl start photo-api promtail telegraf"
echo "환경변수 변경: $ENV_FILE 수정 후 systemctl restart photo-api promtail telegraf"
