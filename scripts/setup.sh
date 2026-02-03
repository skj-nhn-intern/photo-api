#!/bin/bash

# VM 인스턴스 배포용 백엔드 설정 스크립트
# 사용법: sudo ./setup.sh
# Telegraf/Promtail: 바이너리·설정 따로 업로드 가능.
#   바이너리: TELEGRAF_TAR, PROMTAIL_ZIP (기본: $SERVICE_HOME/dist/ 내 파일)
#   설정:    TELEGRAF_CONF, PROMTAIL_CONF (기본: $SERVICE_HOME/conf/ 내 파일)
#   자세한 배치: conf/README.md

set -e  # 에러 발생 시 스크립트 중단

# 서비스 사용자 (선택사항, 기본값: 현재 사용자)
SERVICE_USER="${SUDO_USER:-$USER}"
SERVICE_HOME="/opt/photo-api"
SERVICE_NAME="photo-api"

# 환경 모드 (DEV 또는 PRODUCTION, 기본값: DEV)
ENVIRONMENT="${ENVIRONMENT:-DEV}"

echo "========================================"
echo "백엔드 VM 배포 스크립트"
echo "========================================"
echo ""

# 1. Python 3.11 설치 확인
echo "[1/8] Python 3.11 설치 확인 중..."
if ! command -v python3.11 &> /dev/null; then
    echo "Python 3.11이 설치되어 있지 않습니다."
    echo "Python 3.11을 설치합니다..."
    
    # Ubuntu/Debian
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y software-properties-common
        sudo add-apt-repository -y ppa:deadsnakes/ppa
        sudo apt-get update
        sudo apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip
    # CentOS/RHEL
    elif command -v yum &> /dev/null; then
        sudo yum install -y python311 python311-pip python311-devel
    else
        echo "지원하지 않는 패키지 관리자입니다. Python 3.11을 수동으로 설치해주세요."
        exit 1
    fi
fi

PYTHON_VERSION=$(python3.11 --version)
echo "Python 설치됨: $PYTHON_VERSION"

# 2. 시스템 의존성 설치
echo "[2/8] 시스템 의존성 설치 중..."

# Ubuntu/Debian
if command -v apt-get &> /dev/null; then
    sudo apt-get update
    sudo apt-get install -y \
        gcc \
        g++ \
        make \
        libpq-dev \
        build-essential
# CentOS/RHEL
elif command -v yum &> /dev/null; then
    sudo yum groupinstall -y "Development Tools"
    sudo yum install -y postgresql-devel
fi

echo "시스템 의존성 설치 완료"

# 3. 작업 디렉토리 확인 및 설정
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "[3/8] 작업 디렉토리: $SCRIPT_DIR"

# 서비스 디렉토리 생성
echo "[4/8] 서비스 디렉토리 설정 중..."
sudo mkdir -p "$SERVICE_HOME"
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$SERVICE_HOME"

# 애플리케이션 파일 복사 (프로젝트 루트 = scripts의 부모; conf 포함)
echo "애플리케이션 파일 복사 중..."
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
sudo -u "$SERVICE_USER" cp -r "$REPO_ROOT"/* "$SERVICE_HOME/" 2>/dev/null || \
sudo cp -r "$REPO_ROOT"/* "$SERVICE_HOME/"

# scripts 디렉토리 생성 및 권한 설정
if [ -d "$SERVICE_HOME/scripts" ]; then
    sudo chmod +x "$SERVICE_HOME/scripts"/*.sh 2>/dev/null || true
fi

sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$SERVICE_HOME"

cd "$SERVICE_HOME"
echo "서비스 디렉토리 설정 완료: $SERVICE_HOME"

# 4. 가상환경 생성
echo "[5/8] Python 가상환경 생성 중..."
if [ ! -d "venv" ]; then
    sudo -u "$SERVICE_USER" python3.11 -m venv venv
    echo "가상환경 생성 완료"
else
    echo "가상환경 이미 존재함"
fi

# 5. 의존성 설치
echo "[6/8] Python 의존성 설치 중..."
sudo -u "$SERVICE_USER" ./venv/bin/pip install --upgrade pip
sudo -u "$SERVICE_USER" ./venv/bin/pip install -r requirements.txt
echo "의존성 설치 완료"

# 6. .env 파일 확인
echo "[7/8] 환경 변수 파일 확인 중..."
echo "환경 모드: ${ENVIRONMENT}"

if [ ! -f ".env" ]; then
    echo ".env 파일이 없습니다."
    echo "기본 .env 파일을 생성합니다..."
    
    # 환경 모드에 따라 DEBUG 설정
    if [ "$ENVIRONMENT" = "PRODUCTION" ]; then
        DEBUG_VALUE="False"
        ENV_MODE="PRODUCTION"
    else
        DEBUG_VALUE="True"
        ENV_MODE="DEV"
    fi
    
    sudo -u "$SERVICE_USER" cat > .env << EOF
# Environment
ENVIRONMENT=${ENV_MODE}

# Application
APP_NAME=Photo API
APP_VERSION=1.0.0
DEBUG=${DEBUG_VALUE}
SECRET_KEY=change-me-in-production

# Database
DATABASE_URL=sqlite+aiosqlite:///./photo_api.db

# JWT
JWT_SECRET_KEY=jwt-secret-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# NHN Cloud Object Storage
NHN_STORAGE_IAM_USER=
NHN_STORAGE_IAM_PASSWORD=
NHN_STORAGE_PROJECT_ID=
NHN_STORAGE_TENANT_ID=
NHN_STORAGE_AUTH_URL=https://api-identity-infrastructure.nhncloudservice.com/v2.0
NHN_STORAGE_URL=https://api-storage.nhncloudservice.com/v1
NHN_STORAGE_CONTAINER=photo-container

# NHN Cloud CDN
NHN_CDN_DOMAIN=
NHN_CDN_APP_KEY=
NHN_CDN_SECRET_KEY=
NHN_CDN_ENCRYPT_KEY=
NHN_CDN_TOKEN_EXPIRE_SECONDS=3600

# NHN Cloud Log & Crash
NHN_LOG_APPKEY=
NHN_LOG_URL=https://api-logncrash.nhncloudservice.com/v2/log
NHN_LOG_VERSION=v2
NHN_LOG_PLATFORM=API
EOF
    
    echo ".env 파일을 생성했습니다 (환경: ${ENV_MODE}). 필수 환경 변수를 설정해주세요."
    echo "  nano $SERVICE_HOME/.env"
else
    echo ".env 파일 존재함"
    # 기존 .env 파일에 ENVIRONMENT가 없으면 추가
    if ! grep -q "^ENVIRONMENT=" .env; then
        echo "ENVIRONMENT=${ENVIRONMENT}" >> .env
        echo ".env 파일에 ENVIRONMENT 변수를 추가했습니다."
    fi
fi

# 7. 로그 디렉토리 생성
echo "[8/8] 로그 디렉토리 설정 중..."
LOG_DIR="/var/log/${SERVICE_NAME}"
sudo mkdir -p "$LOG_DIR"
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"
echo "로그 디렉토리 생성 완료: $LOG_DIR"

# 8. systemd 서비스 파일 생성
echo "[9/9] systemd 서비스 설정 중..."

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

sudo tee "$SERVICE_FILE" > /dev/null << EOF
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

# 로그 설정: journald와 파일 모두 저장
# Python logging이 파일과 stdout 모두에 출력하므로,
# stdout/stderr는 journald로, 파일은 직접 저장됨
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME
SyslogFacility=daemon
SyslogLevel=info

# 보안 설정
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# logrotate 설정 파일 생성
LOGROTATE_FILE="/etc/logrotate.d/${SERVICE_NAME}"
sudo tee "$LOGROTATE_FILE" > /dev/null << EOF
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

echo "Logrotate 설정 완료"

# systemd 재로드
sudo systemctl daemon-reload

# 서비스 시작 및 활성화
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "서비스 재시작 중..."
    sudo systemctl restart "$SERVICE_NAME"
else
    echo "서비스 시작 중..."
    sudo systemctl start "$SERVICE_NAME"
fi

# 서비스 자동 시작 설정
sudo systemctl enable "$SERVICE_NAME"

# 서비스 상태 확인
sleep 2
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "서비스 시작 완료"
else
    echo "서비스 시작 실패"
    echo "로그 확인: sudo journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi

# 10. Telegraf / Promtail 설치 (선택: 바이너리·설정 파일 경로를 각각 지정 가능)
# 바이너리: TELEGRAF_TAR, PROMTAIL_ZIP (업로드한 압축 파일 경로)
# 설정:    TELEGRAF_CONF, PROMTAIL_CONF (업로드한 설정 파일 경로, 없으면 SERVICE_HOME/conf/ 사용)
TELEGRAF_INSTALL_DIR="/opt/telegraf"
PROMTAIL_INSTALL_DIR="/opt/promtail"
TELEGRAF_TAR="${TELEGRAF_TAR:-$SERVICE_HOME/dist/telegraf-1.37.1_linux_amd64.tar.gz}"
PROMTAIL_ZIP="${PROMTAIL_ZIP:-$SERVICE_HOME/dist/promtail-linux-amd64.zip}"
TELEGRAF_CONF="${TELEGRAF_CONF:-$SERVICE_HOME/conf/telegraf.conf}"
PROMTAIL_CONF="${PROMTAIL_CONF:-$SERVICE_HOME/conf/promtail-config.yaml}"

if [ -f "$TELEGRAF_TAR" ]; then
    echo ""
    echo "[10a] Telegraf 설치 중... ($TELEGRAF_INSTALL_DIR)"
    sudo mkdir -p "$TELEGRAF_INSTALL_DIR"
    sudo tar -xzf "$TELEGRAF_TAR" -C /opt
    TELEGRAF_EXTRACTED="$(tar -tzf "$TELEGRAF_TAR" | head -1 | cut -d/ -f1)"
    if [ -n "$TELEGRAF_EXTRACTED" ] && [ -d "/opt/$TELEGRAF_EXTRACTED" ]; then
        sudo rm -rf "$TELEGRAF_INSTALL_DIR"
        sudo mv "/opt/$TELEGRAF_EXTRACTED" "$TELEGRAF_INSTALL_DIR"
    fi
    if [ -f "$TELEGRAF_CONF" ]; then
        sudo cp "$TELEGRAF_CONF" "$TELEGRAF_INSTALL_DIR/telegraf.conf"
    fi
    TELEGRAF_BIN="$TELEGRAF_INSTALL_DIR/usr/bin/telegraf"
    [ ! -x "$TELEGRAF_BIN" ] && TELEGRAF_BIN="$TELEGRAF_INSTALL_DIR/telegraf"
    if [ -x "$TELEGRAF_BIN" ]; then
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
        sudo systemctl start telegraf 2>/dev/null || true
        echo "Telegraf 설치 완료 (설정: $TELEGRAF_INSTALL_DIR/telegraf.conf)"
    else
        echo "Telegraf 바이너리를 찾을 수 없습니다. 수동으로 확인 후 systemctl enable/start telegraf"
    fi
else
    echo "[10a] Telegraf 스킵 (바이너리 없음. 바이너리 경로: TELEGRAF_TAR=$TELEGRAF_TAR)"
fi

if [ -f "$PROMTAIL_ZIP" ]; then
    echo ""
    echo "[10b] Promtail 설치 중... ($PROMTAIL_INSTALL_DIR)"
    sudo mkdir -p "$PROMTAIL_INSTALL_DIR"
    sudo unzip -o -q "$PROMTAIL_ZIP" -d "$PROMTAIL_INSTALL_DIR"
    sudo mkdir -p /var/lib/promtail
    sudo chown "$SERVICE_USER:$SERVICE_USER" /var/lib/promtail 2>/dev/null || true
    if [ -f "$PROMTAIL_CONF" ]; then
        sudo cp "$PROMTAIL_CONF" "$PROMTAIL_INSTALL_DIR/config.yaml"
    fi
    PROMTAIL_BIN=""
    for name in promtail-linux-amd64 promtail; do
        [ -x "$PROMTAIL_INSTALL_DIR/$name" ] && PROMTAIL_BIN="$PROMTAIL_INSTALL_DIR/$name" && break
    done
    [ -z "$PROMTAIL_BIN" ] && PROMTAIL_BIN="$(find "$PROMTAIL_INSTALL_DIR" -maxdepth 1 -type f -executable 2>/dev/null | head -1)"
    if [ -n "$PROMTAIL_BIN" ]; then
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
        sudo systemctl start promtail 2>/dev/null || true
        echo "Promtail 설치 완료 (설정: $PROMTAIL_INSTALL_DIR/config.yaml)"
    else
        echo "Promtail 바이너리를 찾을 수 없습니다. 수동 확인 후 systemctl enable/start promtail"
    fi
else
    echo "[10b] Promtail 스킵 (바이너리 없음. 바이너리 경로: PROMTAIL_ZIP=$PROMTAIL_ZIP)"
fi

echo ""
echo "========================================"
echo "배포 완료"
echo "========================================"
echo ""
echo "서비스 정보:"
echo "  - 서비스 이름: $SERVICE_NAME"
echo "  - 설치 경로: $SERVICE_HOME"
echo "  - 서비스 사용자: $SERVICE_USER"
echo "  - 포트: 8000"
echo ""
echo "서비스 관리:"
echo "  sudo systemctl status $SERVICE_NAME"
echo "  sudo systemctl start $SERVICE_NAME"
echo "  sudo systemctl stop $SERVICE_NAME"
echo "  sudo systemctl restart $SERVICE_NAME"
echo ""
echo "로그 확인:"
echo "  # Journald 로그"
echo "  sudo journalctl -u $SERVICE_NAME -f"
echo "  sudo journalctl -u $SERVICE_NAME -n 100"
echo "  $SERVICE_HOME/scripts/view-logs.sh -f    # 실시간 로그"
echo "  $SERVICE_HOME/scripts/view-logs.sh -n 100 # 최근 100줄"
echo "  $SERVICE_HOME/scripts/view-logs.sh -e     # 에러만"
echo ""
echo "  # 파일 로그 (Promtail이 Loki로 전송)"
echo "  tail -f $LOG_DIR/app.log"
echo "  tail -f $LOG_DIR/error.log"
echo "  cat $LOG_DIR/app.log"
echo ""
echo "환경 변수 설정:"
echo "  sudo nano $SERVICE_HOME/.env"
echo "  # 수정 후 서비스 재시작: sudo systemctl restart $SERVICE_NAME"
echo ""
echo "API 접속:"
echo "  http://$(hostname -I | awk '{print $1}'):8000"
echo "  http://localhost:8000"
echo "  Swagger UI: http://localhost:8000/docs"
echo ""
echo "Telegraf / Promtail (바이너리·설정 따로 업로드 시):"
echo "  바이너리 업로드 후: TELEGRAF_TAR=/경로/telegraf-1.37.1_linux_amd64.tar.gz PROMTAIL_ZIP=/경로/promtail-linux-amd64.zip"
echo "  설정 업로드 후:    TELEGRAF_CONF=/경로/telegraf.conf PROMTAIL_CONF=/경로/promtail-config.yaml"
echo "  기본 경로: 바이너리 $SERVICE_HOME/dist/ , 설정 $SERVICE_HOME/conf/"
echo "  설치 결과: Telegraf $TELEGRAF_INSTALL_DIR , Promtail $PROMTAIL_INSTALL_DIR"
echo "  Nginx 예시: $SERVICE_HOME/conf/nginx-photo-api.example.conf"
echo ""
