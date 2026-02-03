#!/usr/bin/env bash
# Ubuntu 인스턴스 이미지 빌드 4단계: Telegraf 설치 및 구성
# 설정: /opt/telegraf/telegraf.conf (conf/telegraf.conf 기반)
# 사용: sudo TELEGRAF_VERSION=1.37.1 ./scripts/4-setup-telegraf.sh
# 환경변수: INFLUX_URL, INFLUX_TOKEN (설정 파일 내 InfluxDB 주소/토큰 덮어쓰기)
set -euo pipefail

TELEGRAF_VERSION="${TELEGRAF_VERSION:-1.37.1}"
TELEGRAF_HOME="/opt/telegraf"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF_SOURCE="${TELEGRAF_CONF_SOURCE:-}"
# 설정은 항상 repo의 ./conf 에서 복사: 스크립트 상위 conf → 2단계에서 복사된 /opt/photo-api/conf
if [[ -z "${CONF_SOURCE}" ]]; then
  for cand in "$SCRIPT_DIR/../conf/telegraf.conf" "/opt/photo-api/conf/telegraf.conf"; do
    if [[ -f "$cand" ]]; then
      CONF_SOURCE="$cand"
      break
    fi
  done
  if [[ -z "${CONF_SOURCE}" ]] || [[ ! -f "$CONF_SOURCE" ]]; then
    echo "오류: conf/telegraf.conf를 찾을 수 없습니다. TELEGRAF_CONF_SOURCE를 지정하세요." >&2
    exit 1
  fi
fi

echo "TELEGRAF_VERSION=$TELEGRAF_VERSION"
echo "TELEGRAF_HOME=$TELEGRAF_HOME"
echo "CONF_SOURCE=$CONF_SOURCE"

echo "[1/5] 디렉터리 생성..."
mkdir -p "$TELEGRAF_HOME"

echo "[2/5] Telegraf 다운로드 및 설치..."
TELEGRAF_TAR="/tmp/telegraf_linux_amd64.tar.gz"
TELEGRAF_URL="https://dl.influxdata.com/telegraf/releases/telegraf-${TELEGRAF_VERSION}_linux_amd64.tar.gz"
curl -sSL -o "$TELEGRAF_TAR" "$TELEGRAF_URL"
tar -xzf "$TELEGRAF_TAR" -C /tmp
rm -f "$TELEGRAF_TAR"
# tar 내부 경로: telegraf-1.37.1/usr/bin/telegraf 등
TELEGRAF_BIN="$(find /tmp -maxdepth 4 -type f -name telegraf 2>/dev/null | head -1)"
if [[ -z "$TELEGRAF_BIN" ]] || [[ ! -x "$TELEGRAF_BIN" ]]; then
  echo "오류: telegraf 바이너리를 찾을 수 없습니다." >&2
  exit 1
fi
cp "$TELEGRAF_BIN" "$TELEGRAF_HOME/telegraf"
rm -rf /tmp/telegraf-*
chmod +x "$TELEGRAF_HOME/telegraf"

echo "[3/5] 설정 파일 복사 (/opt/telegraf/telegraf.conf)..."
cp "$CONF_SOURCE" "$TELEGRAF_HOME/telegraf.conf"
# 선택: INFLUX_URL / INFLUX_TOKEN 환경변수로 덮어쓰기 (배포 시 사용)
if [[ -n "${INFLUX_URL:-}" ]]; then
  sed -i "s|urls = .*|urls = [\"$INFLUX_URL\"]|" "$TELEGRAF_HOME/telegraf.conf"
fi
if [[ -n "${INFLUX_TOKEN:-}" ]]; then
  sed -i "s|token = .*|token = \"$INFLUX_TOKEN\"|" "$TELEGRAF_HOME/telegraf.conf"
fi

echo "[4/5] systemd 서비스 유닛 설치..."
cat > /etc/systemd/system/telegraf.service << 'SVC'
[Unit]
Description=Telegraf - metrics agent for InfluxDB
After=network.target photo-api.service

[Service]
Type=simple
User=root
ExecStart=/opt/telegraf/telegraf --config /opt/telegraf/telegraf.conf
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=telegraf

[Install]
WantedBy=multi-user.target
SVC

echo "[5/5] systemd 리로드 및 서비스 활성화..."
systemctl daemon-reload
systemctl enable telegraf.service

echo "Telegraf 설치 완료. 설정: $TELEGRAF_HOME/telegraf.conf (시작: systemctl start telegraf)"
