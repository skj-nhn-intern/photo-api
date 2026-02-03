#!/usr/bin/env bash
# Ubuntu 인스턴스 이미지 빌드 3단계: Promtail 설치 및 구성
# 설정: /opt/promtail/promtail-config.yaml (conf/promtail-config.yaml 기반)
# 사용: sudo PROMTAIL_VERSION=3.6.4 ./scripts/3-setup-promtail.sh
# 환경변수: LOKI_URL (설정 파일 내 Loki URL 덮어쓰기, 예: http://loki:3100)
set -euo pipefail

PROMTAIL_VERSION="${PROMTAIL_VERSION:-3.6.4}"
PROMTAIL_HOME="/opt/promtail"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_CONF="$SCRIPT_DIR/../conf/promtail-config.yaml"
CONF_SOURCE="${PROMTAIL_CONF_SOURCE:-}"

if [[ -z "${CONF_SOURCE}" ]]; then
  if [[ -f "$DEFAULT_CONF" ]]; then
    CONF_SOURCE="$DEFAULT_CONF"
  else
    echo "오류: promtail-config.yaml을 찾을 수 없습니다. PROMTAIL_CONF_SOURCE를 지정하세요." >&2
    exit 1
  fi
fi

echo "PROMTAIL_VERSION=$PROMTAIL_VERSION"
echo "PROMTAIL_HOME=$PROMTAIL_HOME"
echo "CONF_SOURCE=$CONF_SOURCE"

echo "[1/5] 디렉터리 생성..."
mkdir -p "$PROMTAIL_HOME"
mkdir -p /var/lib/promtail

echo "[2/5] Promtail 바이너리 다운로드 및 설치..."
PROMTAIL_ZIP="/tmp/promtail-linux-amd64.zip"
PROMTAIL_URL="https://github.com/grafana/loki/releases/download/v${PROMTAIL_VERSION}/promtail-linux-amd64.zip"
curl -sSL -o "$PROMTAIL_ZIP" "$PROMTAIL_URL"
unzip -o -q "$PROMTAIL_ZIP" -d "$PROMTAIL_HOME"
rm -f "$PROMTAIL_ZIP"
# 릴리스에 따라 파일명이 promtail-linux-amd64 또는 promtail 일 수 있음
if [[ -f "$PROMTAIL_HOME/promtail-linux-amd64" ]]; then
  mv "$PROMTAIL_HOME/promtail-linux-amd64" "$PROMTAIL_HOME/promtail"
fi
chmod +x "$PROMTAIL_HOME/promtail"

echo "[3/5] 설정 파일 복사 (/opt/promtail/promtail-config.yaml)..."
cp "$CONF_SOURCE" "$PROMTAIL_HOME/promtail-config.yaml"
# 선택: LOKI_URL 환경변수로 Loki 주소 덮어쓰기 (배포 시 사용, 예: http://loki:3100)
if [[ -n "${LOKI_URL:-}" ]]; then
  LOKI_URL="${LOKI_URL%/}"
  sed -i "s|url:.*|url: ${LOKI_URL}/loki/api/v1/push|" "$PROMTAIL_HOME/promtail-config.yaml"
fi

echo "[4/5] systemd 서비스 유닛 설치..."
cat > /etc/systemd/system/promtail.service << 'SVC'
[Unit]
Description=Promtail - log agent for Loki
After=network.target

[Service]
Type=simple
User=root
ExecStart=/opt/promtail/promtail -config.file=/opt/promtail/promtail-config.yaml -config.expand-env=true
Environment=HOSTNAME=%H
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=promtail

[Install]
WantedBy=multi-user.target
SVC

echo "[5/5] systemd 리로드 및 서비스 활성화..."
systemctl daemon-reload
systemctl enable promtail.service

echo "Promtail 설치 완료. 설정: $PROMTAIL_HOME/promtail-config.yaml (시작: systemctl start promtail)"
