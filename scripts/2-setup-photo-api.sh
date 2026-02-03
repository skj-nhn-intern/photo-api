#!/usr/bin/env bash
# Ubuntu 인스턴스 이미지 빌드 2단계: photo-api를 systemd 서비스로 패키징
# 사용: sudo PHOTO_API_SOURCE=/path/to/photo-api ./scripts/2-setup-photo-api.sh
# 기본: PHOTO_API_SOURCE는 스크립트 기준 프로젝트 루트(scripts/../) 또는 /opt/photo-api
set -euo pipefail

SERVICE_HOME="${SERVICE_HOME:-/opt/photo-api}"
PHOTO_API_SOURCE="${PHOTO_API_SOURCE:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_SOURCE="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -z "${PHOTO_API_SOURCE}" ]]; then
  if [[ -f "$DEFAULT_SOURCE/app/main.py" ]] && [[ -f "$DEFAULT_SOURCE/requirements.txt" ]]; then
    PHOTO_API_SOURCE="$DEFAULT_SOURCE"
  else
    PHOTO_API_SOURCE="$SERVICE_HOME"
  fi
fi

echo "PHOTO_API_SOURCE=$PHOTO_API_SOURCE"
echo "SERVICE_HOME=$SERVICE_HOME"

if [[ ! -f "$PHOTO_API_SOURCE/app/main.py" ]] || [[ ! -f "$PHOTO_API_SOURCE/requirements.txt" ]]; then
  echo "오류: app/main.py 또는 requirements.txt를 찾을 수 없습니다. PHOTO_API_SOURCE를 지정하세요." >&2
  exit 1
fi

echo "[1/6] 디렉터리 생성..."
mkdir -p "$SERVICE_HOME"
mkdir -p /var/log/photo-api
chmod 755 /var/log/photo-api

echo "[2/6] photo-api 소스 복사..."
rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' --exclude='venv' \
  "$PHOTO_API_SOURCE/" "$SERVICE_HOME/" 2>/dev/null || {
  cp -a "$PHOTO_API_SOURCE/app" "$PHOTO_API_SOURCE/requirements.txt" "$SERVICE_HOME/"
  [[ -f "$PHOTO_API_SOURCE/alembic.ini" ]] && cp -a "$PHOTO_API_SOURCE/alembic.ini" "$SERVICE_HOME/" || true
  [[ -d "$PHOTO_API_SOURCE/alembic" ]] && cp -a "$PHOTO_API_SOURCE/alembic" "$SERVICE_HOME/" || true
}

echo "[3/6] 전용 사용자 생성 (없으면)..."
id -u photo-api &>/dev/null || useradd -r -s /usr/sbin/nologin -d "$SERVICE_HOME" photo-api 2>/dev/null || true
chown -R photo-api:photo-api "$SERVICE_HOME" /var/log/photo-api 2>/dev/null || chown -R root:root "$SERVICE_HOME" /var/log/photo-api

echo "[4/6] Python 3.11 가상환경 및 의존성 설치..."
"${PYTHON3_11:-python3.11}" -m venv "$SERVICE_HOME/venv"
"$SERVICE_HOME/venv/bin/pip" install --upgrade pip -q
"$SERVICE_HOME/venv/bin/pip" install -r "$SERVICE_HOME/requirements.txt" -q

echo "[5/6] systemd 서비스 유닛 설치..."
cat > /etc/systemd/system/photo-api.service << 'SVC'
[Unit]
Description=Photo API (FastAPI)
After=network.target

[Service]
Type=simple
User=photo-api
Group=photo-api
WorkingDirectory=/opt/photo-api
Environment="PATH=/opt/photo-api/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=-/opt/photo-api/.env
ExecStart=/opt/photo-api/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=photo-api

# 로그 디렉터리 (Promtail 수집용)
ReadWritePaths=/var/log/photo-api

[Install]
WantedBy=multi-user.target
SVC

# User가 없으면 root로 동작하도록 fallback
if ! id -u photo-api &>/dev/null; then
  sed -i 's/User=photo-api/User=root/' /etc/systemd/system/photo-api.service
  sed -i 's/Group=photo-api/Group=root/' /etc/systemd/system/photo-api.service
fi

echo "[6/6] systemd 리로드 및 서비스 활성화..."
systemctl daemon-reload
systemctl enable photo-api.service

# 인스턴스 내 systemctl 실행 스크립트 (시작/중지/재시작/상태)
if [[ -f "$SERVICE_HOME/scripts/run-services.sh" ]]; then
  chmod +x "$SERVICE_HOME/scripts/run-services.sh"
  ln -sf "$SERVICE_HOME/scripts/run-services.sh" /usr/local/bin/photo-api-run 2>/dev/null || true
fi

echo "photo-api systemd 설정 완료. (수동 실행: sudo photo-api-run start|stop|restart|status)"
