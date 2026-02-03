#!/bin/bash
# 4. Telegraf 압축 해제 및 실행
# 사용법: sudo ./4-setup-telegraf.sh
# 바이너리: TELEGRAF_TAR (기본: /opt/photo-api/dist/telegraf-1.37.1_linux_amd64.tar.gz)
# 설정:    TELEGRAF_CONF (기본: /opt/photo-api/conf/telegraf.conf)

set -e

SERVICE_HOME="/opt/photo-api"
TELEGRAF_INSTALL_DIR="/opt/telegraf"
TELEGRAF_CONF="${TELEGRAF_CONF:-$SERVICE_HOME/conf/telegraf.conf}"
SERVICE_NAME="photo-api"

# tar.gz 경로: 환경변수 > /opt/photo-api/dist/ > /opt/telegraf/
if [ -n "${TELEGRAF_TAR:-}" ] && [ -f "$TELEGRAF_TAR" ]; then
    :
elif [ -f "$SERVICE_HOME/dist/telegraf-1.37.1_linux_amd64.tar.gz" ]; then
    TELEGRAF_TAR="$SERVICE_HOME/dist/telegraf-1.37.1_linux_amd64.tar.gz"
elif [ -f "$TELEGRAF_INSTALL_DIR/telegraf-1.37.1_linux_amd64.tar.gz" ]; then
    TELEGRAF_TAR="$TELEGRAF_INSTALL_DIR/telegraf-1.37.1_linux_amd64.tar.gz"
else
    TELEGRAF_TAR="${TELEGRAF_TAR:-$SERVICE_HOME/dist/telegraf-1.37.1_linux_amd64.tar.gz}"
fi

echo "========================================"
echo "[4/4] Telegraf 압축 해제 및 실행"
echo "========================================"
echo ""

if [ ! -f "$TELEGRAF_TAR" ]; then
    echo "Telegraf 바이너리를 찾을 수 없습니다. 다음 경로를 확인하세요:"
    echo "  - $SERVICE_HOME/dist/telegraf-1.37.1_linux_amd64.tar.gz"
    echo "  - $TELEGRAF_INSTALL_DIR/telegraf-1.37.1_linux_amd64.tar.gz"
    echo "다른 경로면: sudo TELEGRAF_TAR=/경로/telegraf-1.37.1_linux_amd64.tar.gz ./4-setup-telegraf.sh"
    exit 1
fi

echo "Telegraf 압축 해제 중... ($TELEGRAF_INSTALL_DIR)"
TMP_EXTRACT="/tmp/telegraf-extract-$$"
sudo rm -rf "$TMP_EXTRACT"
sudo mkdir -p "$TMP_EXTRACT"
sudo tar -xzf "$TELEGRAF_TAR" -C "$TMP_EXTRACT"
# tar 구조: telegraf-1.37.1_linux_amd64/usr/... 이거나 ./usr/... (상위가 . 이면 mv /opt/. 오류 방지)
FIRST=$(sudo ls -1 "$TMP_EXTRACT" 2>/dev/null | head -1)
if [ -n "$FIRST" ] && [ "$FIRST" != "." ] && [ -d "$TMP_EXTRACT/$FIRST" ] && echo "$FIRST" | grep -q '^telegraf'; then
    sudo rm -rf "$TELEGRAF_INSTALL_DIR"
    sudo mv "$TMP_EXTRACT/$FIRST" "$TELEGRAF_INSTALL_DIR"
else
    sudo mkdir -p "$TELEGRAF_INSTALL_DIR"
    sudo mv "$TMP_EXTRACT"/* "$TELEGRAF_INSTALL_DIR/" 2>/dev/null || true
fi
sudo rm -rf "$TMP_EXTRACT"

if [ -f "$TELEGRAF_CONF" ]; then
    sudo cp "$TELEGRAF_CONF" "$TELEGRAF_INSTALL_DIR/telegraf.conf"
    echo "설정 복사: $TELEGRAF_CONF -> $TELEGRAF_INSTALL_DIR/telegraf.conf"
else
    echo "설정 파일 없음: $TELEGRAF_CONF (기본 설정으로 실행됨)"
fi

TELEGRAF_BIN="$TELEGRAF_INSTALL_DIR/usr/bin/telegraf"
[ ! -x "$TELEGRAF_BIN" ] && TELEGRAF_BIN="$TELEGRAF_INSTALL_DIR/telegraf"
if [ ! -x "$TELEGRAF_BIN" ]; then
    echo "Telegraf 실행 파일을 찾을 수 없습니다."
    exit 1
fi

echo "systemd 서비스 등록 중..."
sudo tee /etc/systemd/system/telegraf.service > /dev/null << EOF
[Unit]
Description=Telegraf metrics agent
After=network.target $SERVICE_NAME.service

[Service]
Type=simple
ExecStart=$TELEGRAF_BIN -config $TELEGRAF_INSTALL_DIR/telegraf.conf
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable telegraf
sudo systemctl restart telegraf 2>/dev/null || sudo systemctl start telegraf
sleep 1
if sudo systemctl is-active --quiet telegraf; then
    echo "Telegraf 서비스 시작 완료"
else
    echo "Telegraf 시작 실패. 로그: sudo journalctl -u telegraf -n 30"
fi
echo ""
echo "========================================"
echo "[4/4] 완료. 전체 배포 끝."
echo "========================================"
