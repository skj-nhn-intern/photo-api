#!/bin/bash
# 2. Photo API 압축 해제 및 실행 (프로젝트 복사 → venv → systemd)
# 사용법: sudo ./2-setup-photo-api.sh
# 전제: 1-install-python.sh 실행 완료, 프로젝트 파일이 scripts의 부모(레포 루트)에 있음

set -e

SERVICE_USER="${SUDO_USER:-$USER}"
SERVICE_HOME="/opt/photo-api"
SERVICE_NAME="photo-api"
ENVIRONMENT="${ENVIRONMENT:-DEV}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================"
echo "[2/4] Photo API 배포 및 실행"
echo "========================================"
echo ""

echo "서비스 디렉토리 설정 중..."
sudo mkdir -p "$SERVICE_HOME"
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$SERVICE_HOME"
echo "애플리케이션 파일 복사 중... ($REPO_ROOT -> $SERVICE_HOME)"
sudo -u "$SERVICE_USER" cp -r "$REPO_ROOT"/* "$SERVICE_HOME/" 2>/dev/null || sudo cp -r "$REPO_ROOT"/* "$SERVICE_HOME/"
if [ -d "$SERVICE_HOME/scripts" ]; then
    sudo chmod +x "$SERVICE_HOME/scripts"/*.sh 2>/dev/null || true
fi
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$SERVICE_HOME"
echo "파일 복사 완료"
echo ""

cd "$SERVICE_HOME"

echo "가상환경 생성 중..."
if [ ! -d "venv" ]; then
    sudo -u "$SERVICE_USER" python3.11 -m venv venv
fi
sudo -u "$SERVICE_USER" ./venv/bin/pip install --upgrade pip
sudo -u "$SERVICE_USER" ./venv/bin/pip install -r requirements.txt
echo "의존성 설치 완료"
echo ""

echo "환경 변수 파일 확인 중..."
if [ ! -f ".env" ]; then
    if [ "$ENVIRONMENT" = "PRODUCTION" ]; then
        DEBUG_VALUE="False"
        ENV_MODE="PRODUCTION"
    else
        DEBUG_VALUE="True"
        ENV_MODE="DEV"
    fi
    sudo -u "$SERVICE_USER" cat > .env << EOF
ENVIRONMENT=${ENV_MODE}
APP_NAME=Photo API
APP_VERSION=1.0.0
DEBUG=${DEBUG_VALUE}
SECRET_KEY=change-me-in-production
DATABASE_URL=sqlite+aiosqlite:///./photo_api.db
JWT_SECRET_KEY=jwt-secret-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
NHN_STORAGE_IAM_USER=
NHN_STORAGE_IAM_PASSWORD=
NHN_STORAGE_PROJECT_ID=
NHN_STORAGE_TENANT_ID=
NHN_STORAGE_AUTH_URL=https://api-identity-infrastructure.nhncloudservice.com/v2.0
NHN_STORAGE_URL=https://api-storage.nhncloudservice.com/v1
NHN_STORAGE_CONTAINER=photo-container
NHN_CDN_DOMAIN=
NHN_CDN_APP_KEY=
NHN_CDN_SECRET_KEY=
NHN_CDN_ENCRYPT_KEY=
NHN_CDN_TOKEN_EXPIRE_SECONDS=3600
NHN_LOG_APPKEY=
NHN_LOG_URL=https://api-logncrash.nhncloudservice.com/v2/log
NHN_LOG_VERSION=v2
NHN_LOG_PLATFORM=API
EOF
    echo ".env를 생성했습니다. 필수 값을 설정한 뒤 서비스를 재시작하세요."
else
    echo ".env 존재함"
fi
echo ""

LOG_DIR="/var/log/${SERVICE_NAME}"
echo "로그 디렉토리 생성 중..."
sudo mkdir -p "$LOG_DIR"
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"
echo "로그 디렉토리: $LOG_DIR"
echo ""

echo "systemd 서비스 등록 중..."
sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" > /dev/null << EOF
[Unit]
Description=Photo API Backend Service
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$SERVICE_HOME
Environment="PATH=$SERVICE_HOME/venv/bin"
Environment="PYTHONPATH=$SERVICE_HOME"
Environment="PYTHONUNBUFFERED=1"
ExecStart=$SERVICE_HOME/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo tee "/etc/logrotate.d/${SERVICE_NAME}" > /dev/null << EOF
$LOG_DIR/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 $SERVICE_USER $SERVICE_USER
    sharedscripts
    postrotate
        systemctl reload $SERVICE_NAME > /dev/null 2>&1 || true
    endscript
}
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME" 2>/dev/null || sudo systemctl start "$SERVICE_NAME"
sleep 2
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "Photo API 서비스 시작 완료 (port 8000)"
else
    echo "서비스 시작 실패. 로그: sudo journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi
echo ""
echo "========================================"
echo "[2/4] 완료. 다음: sudo ./3-setup-promtail.sh"
echo "========================================"
