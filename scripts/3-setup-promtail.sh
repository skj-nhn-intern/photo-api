#!/bin/bash
# 3. Promtail 압축 해제 및 실행
# 사용법: sudo ./3-setup-promtail.sh
# 바이너리: PROMTAIL_ZIP (기본: /opt/photo-api/dist/promtail-linux-amd64.zip)
# 설정:    PROMTAIL_CONF (기본: /opt/photo-api/conf/promtail-config.yaml)

set -e

SERVICE_USER="${SUDO_USER:-$USER}"
SERVICE_HOME="/opt/photo-api"
PROMTAIL_INSTALL_DIR="/opt/promtail"
PROMTAIL_CONF="${PROMTAIL_CONF:-$SERVICE_HOME/conf/promtail-config.yaml}"

# zip 경로: 환경변수 > /opt/photo-api/dist/ > /opt/promtail/
if [ -n "${PROMTAIL_ZIP:-}" ] && [ -f "$PROMTAIL_ZIP" ]; then
    :
elif [ -f "$SERVICE_HOME/dist/promtail-linux-amd64.zip" ]; then
    PROMTAIL_ZIP="$SERVICE_HOME/dist/promtail-linux-amd64.zip"
elif [ -f "$PROMTAIL_INSTALL_DIR/promtail-linux-amd64.zip" ]; then
    PROMTAIL_ZIP="$PROMTAIL_INSTALL_DIR/promtail-linux-amd64.zip"
else
    PROMTAIL_ZIP="${PROMTAIL_ZIP:-$SERVICE_HOME/dist/promtail-linux-amd64.zip}"
fi

echo "========================================"
echo "[3/4] Promtail 압축 해제 및 실행"
echo "========================================"
echo ""

if [ ! -f "$PROMTAIL_ZIP" ]; then
    echo "Promtail 바이너리를 찾을 수 없습니다. 다음 경로를 확인하세요:"
    echo "  - $SERVICE_HOME/dist/promtail-linux-amd64.zip"
    echo "  - $PROMTAIL_INSTALL_DIR/promtail-linux-amd64.zip"
    echo "다른 경로면: sudo PROMTAIL_ZIP=/경로/promtail-linux-amd64.zip ./3-setup-promtail.sh"
    exit 1
fi

echo "Promtail 압축 해제 중... ($PROMTAIL_INSTALL_DIR)"
sudo mkdir -p "$PROMTAIL_INSTALL_DIR"
sudo unzip -o -q "$PROMTAIL_ZIP" -d "$PROMTAIL_INSTALL_DIR"
sudo mkdir -p /var/lib/promtail
sudo chown "$SERVICE_USER:$SERVICE_USER" /var/lib/promtail 2>/dev/null || true

if [ -f "$PROMTAIL_CONF" ]; then
    sudo cp "$PROMTAIL_CONF" "$PROMTAIL_INSTALL_DIR/config.yaml"
    echo "설정 복사: $PROMTAIL_CONF -> $PROMTAIL_INSTALL_DIR/config.yaml"
else
    echo "설정 파일 없음: $PROMTAIL_CONF (기본 설정으로 실행됨)"
fi

PROMTAIL_BIN=""
for name in promtail-linux-amd64 promtail; do
    [ -x "$PROMTAIL_INSTALL_DIR/$name" ] && PROMTAIL_BIN="$PROMTAIL_INSTALL_DIR/$name" && break
done
[ -z "$PROMTAIL_BIN" ] && PROMTAIL_BIN="$(find "$PROMTAIL_INSTALL_DIR" -maxdepth 1 -type f -executable 2>/dev/null | head -1)"

if [ -z "$PROMTAIL_BIN" ]; then
    echo "Promtail 실행 파일을 찾을 수 없습니다."
    exit 1
fi

echo "systemd 서비스 등록 중..."
sudo tee /etc/systemd/system/promtail.service > /dev/null << EOF
[Unit]
Description=Promtail log agent (Loki)
After=network.target

[Service]
Type=simple
Environment=HOSTNAME=%H
ExecStart=$PROMTAIL_BIN -config.file=$PROMTAIL_INSTALL_DIR/config.yaml -config.expand-env=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable promtail
sudo systemctl restart promtail 2>/dev/null || sudo systemctl start promtail
sleep 1
if sudo systemctl is-active --quiet promtail; then
    echo "Promtail 서비스 시작 완료"
else
    echo "Promtail 시작 실패. 로그: sudo journalctl -u promtail -n 30"
fi
echo ""
echo "========================================"
echo "[3/4] 완료. 다음: sudo ./4-setup-telegraf.sh"
echo "========================================"
