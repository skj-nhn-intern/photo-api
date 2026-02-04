#!/usr/bin/env bash
# Promtail 설치 스크립트
# 환경변수는 /opt/photo-api/.env 에서 로드
set -euo pipefail

PROMTAIL_VERSION="${PROMTAIL_VERSION:-3.6.4}"
PROMTAIL_HOME="/opt/promtail"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 설정 파일 찾기
CONF_SOURCE=""
for cand in "$SCRIPT_DIR/../conf/promtail-config.yaml" "/opt/photo-api/conf/promtail-config.yaml"; do
  if [[ -f "$cand" ]]; then
    CONF_SOURCE="$cand"
    break
  fi
done
if [[ -z "$CONF_SOURCE" ]]; then
  echo "오류: promtail-config.yaml을 찾을 수 없습니다." >&2
  exit 1
fi

echo "PROMTAIL_VERSION=$PROMTAIL_VERSION"
echo "CONF_SOURCE=$CONF_SOURCE"

echo "[1/4] 디렉터리 생성..."
mkdir -p "$PROMTAIL_HOME"
mkdir -p /var/lib/promtail
mkdir -p /var/log/photo-api
chmod 755 /var/log/photo-api

if [[ -x "$PROMTAIL_HOME/promtail" ]]; then
  echo "[2/4] Promtail 이미 존재, 다운로드 생략"
else
  echo "[2/4] Promtail 다운로드..."
  curl -sSL -o /tmp/promtail.zip \
    "https://github.com/grafana/loki/releases/download/v${PROMTAIL_VERSION}/promtail-linux-amd64.zip"
  unzip -o -q /tmp/promtail.zip -d "$PROMTAIL_HOME"
  rm -f /tmp/promtail.zip
  [[ -f "$PROMTAIL_HOME/promtail-linux-amd64" ]] && mv "$PROMTAIL_HOME/promtail-linux-amd64" "$PROMTAIL_HOME/promtail"
  chmod +x "$PROMTAIL_HOME/promtail"
fi

echo "[3/4] 설정 파일 복사..."
cp "$CONF_SOURCE" "$PROMTAIL_HOME/promtail-config.yaml"

echo "[4/4] systemd 서비스 설치..."
cat > /etc/systemd/system/promtail.service << 'EOF'
[Unit]
Description=Promtail
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/opt/photo-api/.env
ExecStart=/opt/promtail/promtail -config.file=/opt/promtail/promtail-config.yaml -config.expand-env=true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable promtail.service

echo "Promtail 설정 완료."
