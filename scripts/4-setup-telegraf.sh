#!/usr/bin/env bash
# Telegraf 설치 스크립트
# 사용: sudo ./scripts/4-setup-telegraf.sh
set -euo pipefail

TELEGRAF_VERSION="${TELEGRAF_VERSION:-1.37.1}"
TELEGRAF_HOME="/opt/telegraf"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 설정 파일 찾기
CONF_SOURCE=""
for cand in "$SCRIPT_DIR/../conf/telegraf.conf" "/opt/photo-api/conf/telegraf.conf"; do
  if [[ -f "$cand" ]]; then
    CONF_SOURCE="$cand"
    break
  fi
done
if [[ -z "$CONF_SOURCE" ]]; then
  echo "오류: telegraf.conf를 찾을 수 없습니다." >&2
  exit 1
fi

echo "TELEGRAF_VERSION=$TELEGRAF_VERSION"
echo "CONF_SOURCE=$CONF_SOURCE"

echo "[1/4] 디렉터리 생성..."
mkdir -p "$TELEGRAF_HOME"

echo "[2/4] Telegraf 다운로드..."
curl -sSL -o /tmp/telegraf.tar.gz \
  "https://dl.influxdata.com/telegraf/releases/telegraf-${TELEGRAF_VERSION}_linux_amd64.tar.gz"
tar -xzf /tmp/telegraf.tar.gz -C /tmp
rm -f /tmp/telegraf.tar.gz

TELEGRAF_BIN="$(find /tmp -maxdepth 4 -type f -name telegraf 2>/dev/null | head -1)"
if [[ -z "$TELEGRAF_BIN" ]]; then
  echo "오류: telegraf 바이너리를 찾을 수 없습니다." >&2
  exit 1
fi

# 실행 중이면 중지
systemctl is-active --quiet telegraf.service 2>/dev/null && systemctl stop telegraf.service || true
cp "$TELEGRAF_BIN" "$TELEGRAF_HOME/telegraf"
rm -rf /tmp/telegraf-*
chmod +x "$TELEGRAF_HOME/telegraf"

echo "[3/4] 설정 파일 복사..."
cp "$CONF_SOURCE" "$TELEGRAF_HOME/telegraf.conf"

echo "[4/4] systemd 서비스 설치..."
cat > /etc/systemd/system/telegraf.service << 'EOF'
[Unit]
Description=Telegraf
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/telegraf/telegraf --config /opt/telegraf/telegraf.conf
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable telegraf.service

echo "완료. 시작: sudo systemctl start telegraf"
