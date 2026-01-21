#!/bin/bash

# VM 인스턴스 배포용 백엔드 설정 스크립트
# 사용법: sudo ./setup.sh

set -e  # 에러 발생 시 스크립트 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 서비스 사용자 (선택사항, 기본값: 현재 사용자)
SERVICE_USER="${SUDO_USER:-$USER}"
SERVICE_HOME="/opt/photo-api"
SERVICE_NAME="photo-api"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}백엔드 VM 배포 스크립트${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 1. Python 3.11 설치 확인
echo -e "${YELLOW}[1/8] Python 3.11 설치 확인 중...${NC}"
if ! command -v python3.11 &> /dev/null; then
    echo -e "${RED}Python 3.11이 설치되어 있지 않습니다.${NC}"
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
        echo -e "${RED}지원하지 않는 패키지 관리자입니다. Python 3.11을 수동으로 설치해주세요.${NC}"
        exit 1
    fi
fi

PYTHON_VERSION=$(python3.11 --version)
echo -e "${GREEN}✅ Python 설치됨: $PYTHON_VERSION${NC}"

# 2. 시스템 의존성 설치
echo -e "${YELLOW}[2/8] 시스템 의존성 설치 중...${NC}"

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

echo -e "${GREEN}✅ 시스템 의존성 설치 완료${NC}"

# 3. 작업 디렉토리 확인 및 설정
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo -e "${YELLOW}[3/8] 작업 디렉토리: $SCRIPT_DIR${NC}"

# 서비스 디렉토리 생성
echo -e "${YELLOW}[4/8] 서비스 디렉토리 설정 중...${NC}"
sudo mkdir -p "$SERVICE_HOME"
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$SERVICE_HOME"

# 애플리케이션 파일 복사
echo "애플리케이션 파일 복사 중..."
sudo -u "$SERVICE_USER" cp -r "$SCRIPT_DIR"/* "$SERVICE_HOME/" 2>/dev/null || \
sudo cp -r "$SCRIPT_DIR"/* "$SERVICE_HOME/"
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$SERVICE_HOME"

cd "$SERVICE_HOME"
echo -e "${GREEN}✅ 서비스 디렉토리 설정 완료: $SERVICE_HOME${NC}"

# 4. 가상환경 생성
echo -e "${YELLOW}[5/8] Python 가상환경 생성 중...${NC}"
if [ ! -d "venv" ]; then
    sudo -u "$SERVICE_USER" python3.11 -m venv venv
    echo -e "${GREEN}✅ 가상환경 생성 완료${NC}"
else
    echo -e "${GREEN}✅ 가상환경 이미 존재함${NC}"
fi

# 5. 의존성 설치
echo -e "${YELLOW}[6/8] Python 의존성 설치 중...${NC}"
sudo -u "$SERVICE_USER" ./venv/bin/pip install --upgrade pip
sudo -u "$SERVICE_USER" ./venv/bin/pip install -r requirements.txt
echo -e "${GREEN}✅ 의존성 설치 완료${NC}"

# 6. .env 파일 확인
echo -e "${YELLOW}[7/8] 환경 변수 파일 확인 중...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env 파일이 없습니다.${NC}"
    echo "기본 .env 파일을 생성합니다..."
    
    sudo -u "$SERVICE_USER" cat > .env << 'EOF'
# Application
APP_NAME=Photo API
APP_VERSION=1.0.0
DEBUG=False
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
    
    echo -e "${YELLOW}⚠️  .env 파일을 생성했습니다. 필수 환경 변수를 설정해주세요.${NC}"
    echo "  nano $SERVICE_HOME/.env"
else
    echo -e "${GREEN}✅ .env 파일 존재함${NC}"
fi

# 7. systemd 서비스 파일 생성
echo -e "${YELLOW}[8/8] systemd 서비스 설정 중...${NC}"

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
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

# 보안 설정
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

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
    echo -e "${GREEN}✅ 서비스 시작 완료${NC}"
else
    echo -e "${RED}❌ 서비스 시작 실패${NC}"
    echo "로그 확인: sudo journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}배포 완료!${NC}"
echo -e "${GREEN}========================================${NC}"
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
echo "  sudo journalctl -u $SERVICE_NAME -f"
echo "  sudo journalctl -u $SERVICE_NAME -n 100"
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
