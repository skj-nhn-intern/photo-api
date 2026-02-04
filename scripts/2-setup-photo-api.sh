#!/usr/bin/env bash
# photo-api를 systemd 서비스로 패키징
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
  echo "오류: app/main.py 또는 requirements.txt를 찾을 수 없습니다." >&2
  exit 1
fi

echo "[1/6] 디렉터리 생성..."
mkdir -p "$SERVICE_HOME"
mkdir -p /var/log/photo-api
chmod 755 /var/log/photo-api

echo "[2/6] photo-api 소스 복사..."
rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='venv' \
  "$PHOTO_API_SOURCE/" "$SERVICE_HOME/" 2>/dev/null || {
  cp -a "$PHOTO_API_SOURCE/app" "$PHOTO_API_SOURCE/requirements.txt" "$SERVICE_HOME/"
  [[ -f "$PHOTO_API_SOURCE/.env" ]] && cp -a "$PHOTO_API_SOURCE/.env" "$SERVICE_HOME/" || true
  [[ -d "$PHOTO_API_SOURCE/conf" ]] && cp -a "$PHOTO_API_SOURCE/conf" "$SERVICE_HOME/" || true
}

echo "[3/6] 전용 사용자 생성..."
id -u photo-api &>/dev/null || useradd -r -s /usr/sbin/nologin -d "$SERVICE_HOME" photo-api 2>/dev/null || true
chown -R photo-api:photo-api "$SERVICE_HOME" /var/log/photo-api 2>/dev/null || chown -R root:root "$SERVICE_HOME" /var/log/photo-api

echo "[4/6] Python 가상환경 및 의존성 설치..."
if [[ -x "$SERVICE_HOME/venv/bin/uvicorn" ]]; then
  echo "  venv 이미 존재(uvicorn 있음), pip 설치 생략"
else
  "${PYTHON3_11:-python3.11}" -m venv "$SERVICE_HOME/venv"
  "$SERVICE_HOME/venv/bin/pip" install --upgrade pip -q
  "$SERVICE_HOME/venv/bin/pip" install -r "$SERVICE_HOME/requirements.txt" -q
fi

echo "[5/6] systemd 서비스 유닛 설치..."
cat > /etc/systemd/system/photo-api.service << 'SVC'
[Unit]
Description=Photo API
After=network.target

[Service]
Type=simple
User=photo-api
Group=photo-api
WorkingDirectory=/opt/photo-api
Environment="PATH=/opt/photo-api/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/opt/photo-api/.env
ExecStart=/opt/photo-api/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=photo-api
ReadWritePaths=/var/log/photo-api

[Install]
WantedBy=multi-user.target
SVC

if ! id -u photo-api &>/dev/null; then
  sed -i 's/User=photo-api/User=root/' /etc/systemd/system/photo-api.service
  sed -i 's/Group=photo-api/Group=root/' /etc/systemd/system/photo-api.service
fi

echo "[6/6] systemd 리로드..."
systemctl daemon-reload
systemctl enable photo-api.service

echo "photo-api 설정 완료."
