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
if [[ -x "$SERVICE_HOME/venv/bin/gunicorn" ]] && [[ -x "$SERVICE_HOME/venv/bin/uvicorn" ]]; then
  echo "  venv 이미 존재(gunicorn/uvicorn 있음), pip 설치 생략"
else
  "${PYTHON3_11:-python3.11}" -m venv "$SERVICE_HOME/venv"
  "$SERVICE_HOME/venv/bin/pip" install --upgrade pip -q
  "$SERVICE_HOME/venv/bin/pip" install -r "$SERVICE_HOME/requirements.txt" -q
fi

echo "[5/6] systemd 서비스 유닛 설치..."
# Gunicorn + Uvicorn worker 설정 (환경변수 또는 기본값)
GUNICORN_WORKERS="${GUNICORN_WORKERS:-${UVICORN_WORKERS:-4}}"
GUNICORN_MAX_REQUESTS="${GUNICORN_MAX_REQUESTS:-${UVICORN_LIMIT_MAX_REQUESTS:-20000}}"
GUNICORN_MAX_REQUESTS_JITTER="${GUNICORN_MAX_REQUESTS_JITTER:-${UVICORN_LIMIT_MAX_REQUESTS_JITTER:-2000}}"
GUNICORN_KEEP_ALIVE="${GUNICORN_KEEP_ALIVE:-${UVICORN_TIMEOUT_KEEP_ALIVE:-5}}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-120}"
# Uvicorn worker용 (워커 내부 limit-concurrency 등)
export UVICORN_LIMIT_CONCURRENCY="${UVICORN_LIMIT_CONCURRENCY:-2000}"

# Gunicorn 명령어 구성 (Uvicorn Worker 사용, max_requests + jitter)
GUNICORN_CMD="$SERVICE_HOME/venv/bin/gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000"
GUNICORN_CMD="$GUNICORN_CMD --workers $GUNICORN_WORKERS"
GUNICORN_CMD="$GUNICORN_CMD --max-requests $GUNICORN_MAX_REQUESTS --max-requests-jitter $GUNICORN_MAX_REQUESTS_JITTER"
GUNICORN_CMD="$GUNICORN_CMD --keep-alive $GUNICORN_KEEP_ALIVE --timeout $GUNICORN_TIMEOUT"

cat > /etc/systemd/system/photo-api.service << SVC
[Unit]
Description=Photo API
After=network.target

[Service]
Type=simple
User=photo-api
Group=photo-api
WorkingDirectory=/opt/photo-api
Environment="PATH=/opt/photo-api/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="UVICORN_LIMIT_CONCURRENCY=$UVICORN_LIMIT_CONCURRENCY"
EnvironmentFile=/opt/photo-api/.env
ExecStart=$GUNICORN_CMD
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=photo-api
ReadWritePaths=/var/log/photo-api
# 메모리 최적화: 메모리 제한 설정 (8GB RAM 환경 고려)
MemoryMax=6G
MemoryHigh=5G
# CPU 제한 (선택적, 4vCPU 환경 고려)
CPUQuota=300%

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
