#!/bin/bash

# Photo API 실행 스크립트
# NHN Cloud Deploy User Command용
# 사용법: ./run-photo-api.sh

set -e

# 설정
APP_DIR="${APP_DIR:-/opt/photo-api}"
ZIP_FILE="${APP_DIR}/photo-api.zip"
ENVIRONMENT="${ENVIRONMENT:-DEV}"

echo "========================================"
echo "Photo API 실행 스크립트"
echo "========================================"
echo ""
echo "애플리케이션 디렉토리: ${APP_DIR}"
echo "환경 모드: ${ENVIRONMENT}"
echo ""

# 0. 디렉토리 생성
echo "[0/9] 디렉토리 확인 중..."
if [ ! -d "$APP_DIR" ]; then
    echo "Target Directory '$APP_DIR' is not exist.. make new directory.."
    mkdir -p "$APP_DIR"
    echo "Success"
fi
echo "OK: 디렉토리 확인 완료: $APP_DIR"

# 1. 압축 파일 확인
echo "[1/9] 압축 파일 확인 중..."
if [ ! -f "$ZIP_FILE" ]; then
    echo "ERROR: 압축 파일을 찾을 수 없습니다: $ZIP_FILE"
    exit 1
fi
echo "OK: 압축 파일 확인: $ZIP_FILE"

# 2. 작업 디렉토리로 이동
echo "[2/9] 작업 디렉토리 설정 중..."
cd "$APP_DIR"
echo "OK: 작업 디렉토리: $(pwd)"

# 3. 기존 파일 정리
echo "[3/9] 기존 파일 정리 중..."
if [ -d "app" ]; then
    rm -rf app
fi
if [ -d "__pycache__" ]; then
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
fi
if [ -f "photo-api.zip" ]; then
    find . -maxdepth 1 -type f ! -name "photo-api.zip" ! -name "*.sh" -delete 2>/dev/null || true
    find . -maxdepth 1 -type d ! -name "venv" ! -name "." ! -name ".." -exec rm -rf {} + 2>/dev/null || true
fi
echo "OK: 파일 정리 완료"

# 4. 압축 해제
echo "[4/9] 압축 파일 해제 중..."
# 현재 디렉토리(APP_DIR)에 압축 해제
unzip -q -o photo-api.zip

# 압축 해제 후 photo-api 디렉토리가 생성되었는지 확인
if [ -d "photo-api" ]; then
    echo "압축 파일 내부에 photo-api 디렉토리가 있습니다. 파일을 상위 디렉토리로 이동합니다..."
    mv photo-api/* . 2>/dev/null || true
    mv photo-api/.* . 2>/dev/null || true
    rmdir photo-api 2>/dev/null || true
fi

echo "OK: 압축 해제 완료"

# 5. Python 가상환경 설정
echo "[5/9] Python 가상환경 설정 중..."

# Python 3.11 확인
if ! command -v python3.11 &> /dev/null; then
    echo "ERROR: Python 3.11이 설치되어 있지 않습니다."
    echo "먼저 setup-python.sh를 실행해주세요."
    exit 1
fi

# 가상환경 생성 또는 업데이트
if [ ! -d "venv" ]; then
    echo "가상환경 생성 중..."
    python3.11 -m venv venv
    echo "OK: 가상환경 생성 완료"
else
    echo "OK: 가상환경 이미 존재함"
fi

# pip 업그레이드
echo "pip 업그레이드 중..."
./venv/bin/pip install --upgrade pip setuptools wheel --quiet

# 의존성 설치
echo "Python 의존성 설치 중..."
if [ -f "requirements.txt" ]; then
    ./venv/bin/pip install -r requirements.txt --quiet
    echo "OK: 의존성 설치 완료"
else
    echo "WARNING: requirements.txt를 찾을 수 없습니다."
fi

# 6. .env 파일 확인
echo "[6/9] 환경 변수 파일 확인 중..."
if [ ! -f ".env" ]; then
    echo "ERROR: .env 파일이 없습니다."
    echo ".env 파일을 생성하고 필수 환경 변수를 설정해주세요."
    exit 1
fi
echo "OK: .env 파일 존재함"

# scripts 디렉토리 권한 설정
if [ -d "scripts" ]; then
    chmod +x scripts/*.sh 2>/dev/null || true
fi

# 7. 실행 wrapper 스크립트 생성
echo "[7/9] 실행 스크립트 생성 중..."
WRAPPER_SCRIPT="${APP_DIR}/start-photo-api.sh"
cat > "$WRAPPER_SCRIPT" << 'WRAPPER_EOF'
#!/bin/bash
# Photo API 실행 wrapper 스크립트
# .env 파일을 로드하고 uvicorn 실행
# APP_DIR은 아래 한 줄만 치환됩니다.

APP_DIR="__APP_DIR__"
cd "$APP_DIR" || {
    echo "ERROR: Cannot change to directory: $APP_DIR" >&2
    exit 1
}

# .env 파일이 있으면 로드 (안전하게 파싱)
if [ -f ".env" ]; then
    # .env 파일을 안전하게 파싱하여 환경 변수로 설정
    # 주석과 빈 줄 무시, 값에 공백이 있어도 처리
    while IFS= read -r line || [ -n "$line" ]; do
        # 주석과 빈 줄 건너뛰기
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line// }" ]] && continue
        
        # KEY=VALUE 형식 파싱
        if [[ "$line" =~ ^[[:space:]]*([^=]+)=(.*)$ ]]; then
            key="${BASH_REMATCH[1]// /}"
            value="${BASH_REMATCH[2]}"
            
            # 값의 앞뒤 공백 제거
            value="${value#"${value%%[![:space:]]*}"}"
            value="${value%"${value##*[![:space:]]}"}"
            
            # 값이 따옴표로 감싸져 있으면 제거
            if [[ "$value" =~ ^\".*\"$ ]] || [[ "$value" =~ ^\'.*\'$ ]]; then
                value="${value:1:-1}"
            fi
            
            # 환경 변수로 설정 (export)
            # 값에 KEY= 접두사가 있으면 제거 (예: DATABASE_URL=DATABASE_URL=...)
            if [[ "$value" =~ ^${key}= ]]; then
                value="${value#${key}=}"
            fi
            export "$key=$value"
        fi
    done < .env
else
    echo "WARNING: .env file not found in $APP_DIR" >&2
fi

# Python 가상환경 확인
if [ ! -f "$APP_DIR/venv/bin/uvicorn" ]; then
    echo "ERROR: uvicorn not found at $APP_DIR/venv/bin/uvicorn" >&2
    exit 1
fi

# uvicorn 실행
exec "$APP_DIR/venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000
WRAPPER_EOF

# 부모 스크립트의 APP_DIR을 wrapper에 반영 (동일 경로에서 .env/venv 사용)
sed "s#__APP_DIR__#$APP_DIR#g" "$WRAPPER_SCRIPT" > "${WRAPPER_SCRIPT}.tmp" && mv "${WRAPPER_SCRIPT}.tmp" "$WRAPPER_SCRIPT"

chmod +x "$WRAPPER_SCRIPT"
echo "OK: 실행 스크립트 생성 완료: $WRAPPER_SCRIPT"

# wrapper 스크립트 테스트 (구문 확인)
echo "wrapper 스크립트 구문 확인 중..."
if bash -n "$WRAPPER_SCRIPT"; then
    echo "OK: wrapper 스크립트 구문 확인 완료"
else
    echo "ERROR: wrapper 스크립트 구문 오류"
    exit 1
fi

# 서비스 사용자 결정 (미리 결정)
if [ -n "$SUDO_USER" ]; then
    SERVICE_USER="$SUDO_USER"
elif [ -n "$USER" ] && [ "$USER" != "root" ]; then
    SERVICE_USER="$USER"
else
    SERVICE_USER=$(getent passwd | awk -F: '$3 >= 1000 && $1 != "nobody" {print $1; exit}')
    if [ -z "$SERVICE_USER" ]; then
        SERVICE_USER="root"
        echo "WARNING: 서비스 사용자를 찾을 수 없어 root로 설정합니다."
    fi
fi

# 8. 로그 디렉토리 생성
echo "[8/9] 로그 디렉토리 설정 중..."
SERVICE_NAME="photo-api"
LOG_DIR="/var/log/${SERVICE_NAME}"
sudo mkdir -p "$LOG_DIR"
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR" 2>/dev/null || true
echo "OK: 로그 디렉토리 생성 완료: $LOG_DIR"

# 9. systemd 서비스 파일 생성
echo "[9/9] systemd 서비스 설정 중..."
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "서비스 사용자: $SERVICE_USER"

# wrapper 스크립트 및 앱 디렉토리 소유권 설정
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR" 2>/dev/null || true

sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=Photo API Backend Service
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
Environment="PYTHONPATH=$APP_DIR"
Environment="PYTHONUNBUFFERED=1"
ExecStart=$WRAPPER_SCRIPT
Restart=always
RestartSec=10

# 로그 설정: journald와 파일 모두 저장
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

echo "OK: systemd 서비스 파일 생성 완료"

# systemd 재로드
sudo systemctl daemon-reload

# 9. 서비스 시작 및 활성화
echo "[9/9] 서비스 시작 중..."
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
sleep 3
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "OK: 서비스 시작 완료"
else
    echo ""
    echo "========================================"
    echo "ERROR: 서비스 시작 실패"
    echo "========================================"
    echo ""
    
    echo "=== 서비스 상태 ==="
    sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
    echo ""
    
    echo "=== 최근 로그 (최대 100줄) ==="
    sudo journalctl -u "$SERVICE_NAME" -n 100 --no-pager || true
    echo ""
    
    echo "=== 디버깅 정보 ==="
    echo "Wrapper 스크립트: $WRAPPER_SCRIPT"
    if [ -f "$WRAPPER_SCRIPT" ]; then
        echo "  존재 여부: YES"
        echo "  실행 권한: $([ -x "$WRAPPER_SCRIPT" ] && echo "YES" || echo "NO")"
        echo "  소유자: $(ls -l "$WRAPPER_SCRIPT" | awk '{print $3":"$4}')"
    else
        echo "  존재 여부: NO"
    fi
    
    echo ""
    echo "Python 경로: $APP_DIR/venv/bin/uvicorn"
    if [ -f "$APP_DIR/venv/bin/uvicorn" ]; then
        echo "  존재 여부: YES"
        echo "  실행 권한: $([ -x "$APP_DIR/venv/bin/uvicorn" ] && echo "YES" || echo "NO")"
    else
        echo "  존재 여부: NO"
    fi
    
    echo ""
    echo ".env 파일: $APP_DIR/.env"
    if [ -f "$APP_DIR/.env" ]; then
        echo "  존재 여부: YES"
        echo "  읽기 권한: $([ -r "$APP_DIR/.env" ] && echo "YES" || echo "NO")"
    else
        echo "  존재 여부: NO"
    fi
    
    echo ""
    echo "서비스 사용자: $SERVICE_USER"
    echo "앱 디렉토리 소유자: $(ls -ld "$APP_DIR" | awk '{print $3":"$4}')"
    echo ""
    
    echo "=== 수동 실행 테스트 ==="
    echo "다음 명령어로 수동 실행하여 에러를 확인하세요:"
    echo "  cd $APP_DIR"
    echo "  bash $WRAPPER_SCRIPT"
    echo ""
    echo "또는:"
    echo "  cd $APP_DIR"
    echo "  source .env"
    echo "  ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"
    echo ""
    
    exit 1
fi

echo ""
echo "========================================"
echo "설치 완료!"
echo "========================================"
echo ""
echo "애플리케이션 정보:"
echo "  - 설치 경로: $APP_DIR"
echo "  - 환경 모드: $ENVIRONMENT"
echo "  - Python: $(./venv/bin/python --version)"
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
echo "  tail -f $LOG_DIR/app.log"
echo "  tail -f $LOG_DIR/error.log"
echo ""
