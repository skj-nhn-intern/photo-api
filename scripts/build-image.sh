#!/usr/bin/env bash
# Ubuntu 인스턴스 이미지 빌드: 1~4단계 순차 실행
# Packer/이미지 빌드 VM에서 실행하거나, 새 Ubuntu 인스턴스에서 한 번에 설정할 때 사용
#
# 사용법:
#   export LOKI_URL=http://loki:3100
#   export INFLUX_URL=http://influx:8086 INFLUX_TOKEN=... INFLUX_ORG=... INFLUX_BUCKET=...
#   sudo -E ./scripts/build-image.sh
#
# 환경변수 (필수):
#   LOKI_URL      - Loki 서버 URL (예: http://192.168.4.73:3100)
#   INFLUX_URL    - InfluxDB 서버 URL
#   INFLUX_TOKEN  - InfluxDB 인증 토큰
#   INFLUX_ORG    - InfluxDB 조직명
#   INFLUX_BUCKET - InfluxDB 버킷명
# 환경변수 (선택):
#   INSTANCE_IP   - 인스턴스 IP (미설정 시 자동 감지)
#   PROMTAIL_VERSION, TELEGRAF_VERSION
#
# 환경변수 변경 시:
#   /etc/default/photo-api 파일 수정 후 systemctl restart <서비스>
set -euo pipefail

ENV_FILE="/etc/default/photo-api"

# 필수 환경변수 검증
missing=()
[[ -z "${LOKI_URL:-}" ]] && missing+=("LOKI_URL")
[[ -z "${INFLUX_URL:-}" ]] && missing+=("INFLUX_URL")
[[ -z "${INFLUX_TOKEN:-}" ]] && missing+=("INFLUX_TOKEN")
[[ -z "${INFLUX_ORG:-}" ]] && missing+=("INFLUX_ORG")
[[ -z "${INFLUX_BUCKET:-}" ]] && missing+=("INFLUX_BUCKET")

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "오류: 필수 환경변수가 설정되지 않았습니다: ${missing[*]}" >&2
  echo "사용법: sudo -E $0  (환경변수를 먼저 export 후 실행)" >&2
  exit 1
fi

# INSTANCE_IP 자동 감지
INSTANCE_IP="${INSTANCE_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
INSTANCE_IP="${INSTANCE_IP:-127.0.0.1}"

echo "=== 환경변수를 $ENV_FILE 에 저장 ==="
cat > "$ENV_FILE" << EOF
# photo-api, promtail, telegraf 서비스 환경변수
# 수정 후: sudo systemctl restart photo-api promtail telegraf

# Promtail -> Loki
LOKI_URL=$LOKI_URL
INSTANCE_IP=$INSTANCE_IP

# Telegraf -> InfluxDB
INFLUX_URL=$INFLUX_URL
INFLUX_TOKEN=$INFLUX_TOKEN
INFLUX_ORG=$INFLUX_ORG
INFLUX_BUCKET=$INFLUX_BUCKET
EOF
chmod 600 "$ENV_FILE"
echo "  저장 완료: $ENV_FILE"
cat "$ENV_FILE"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
# 실행 권한 없이도 동작하도록 chmod (clone 후 바로 실행 가능)
chmod +x 1-install-python.sh 2-setup-photo-api.sh 3-setup-promtail.sh 4-setup-telegraf.sh run-services.sh 2>/dev/null || true

echo "=== 1/4 Python 3.11 설치 ==="
bash "$SCRIPT_DIR/1-install-python.sh"

echo "=== 2/4 photo-api systemd 패키징 ==="
bash "$SCRIPT_DIR/2-setup-photo-api.sh"

echo "=== 3/4 Promtail 설치 및 구성 ==="
bash "$SCRIPT_DIR/3-setup-promtail.sh"

echo "=== 4/4 Telegraf 설치 및 구성 ==="
bash "$SCRIPT_DIR/4-setup-telegraf.sh"

echo "=== 이미지 빌드 스크립트 완료 ==="
echo "서비스 시작: systemctl start photo-api promtail telegraf"
echo "상태 확인: systemctl status photo-api promtail telegraf"
echo ""
echo "환경변수 변경: $ENV_FILE 수정 후 systemctl restart <서비스>"
