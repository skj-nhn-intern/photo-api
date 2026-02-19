#!/usr/bin/env bash
#
# NHN Deploy User Command용: 환경 변수 반영 후 photo-api 서비스 재시작.
# 스크립트에서 앱용 환경 변수를 export 한 뒤 .env에 씁니다.
#
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-photo-api}"
ENV_FILE="${ENV_FILE:-/opt/photo-api/.env}"
LOKI_URL_DEFAULT="${LOKI_URL_DEFAULT:-http://192.168.4.73:3100}"

# app/config.py 기준 환경 변수 (계정/비밀 제외한 항목에 기본값 사용)
ENV_KEYS=(
  ENVIRONMENT
  APP_NAME
  APP_VERSION
  DEBUG
  DATABASE_URL
  JWT_SECRET_KEY
  JWT_ALGORITHM
  ACCESS_TOKEN_EXPIRE_MINUTES
  INSTANCE_IP
  LOKI_URL
  PROMETHEUS_PUSHGATEWAY_URL
  PROMETHEUS_PUSH_INTERVAL_SECONDS
  LOG_TIMEZONE
  LOG_DIR
  NODE_NAME
  NHN_STORAGE_IAM_USER
  NHN_STORAGE_IAM_PASSWORD
  NHN_STORAGE_USERNAME
  NHN_STORAGE_PASSWORD
  NHN_STORAGE_PROJECT_ID
  NHN_STORAGE_TENANT_ID
  NHN_STORAGE_AUTH_URL
  NHN_STORAGE_CONTAINER
  NHN_STORAGE_URL
  NHN_S3_ACCESS_KEY
  NHN_S3_SECRET_KEY
  NHN_S3_ENDPOINT_URL
  NHN_S3_REGION_NAME
  NHN_S3_PRESIGNED_URL_EXPIRE_SECONDS
  NHN_STORAGE_TEMP_URL_KEY
  NHN_CDN_DOMAIN
  NHN_CDN_APP_KEY
  NHN_CDN_SECRET_KEY
  NHN_CDN_ENCRYPT_KEY
)

# 기본값 상수 (계정/비밀은 비움)
DEFAULT_ENVIRONMENT=""
DEFAULT_APP_NAME="Photo API"
DEFAULT_APP_VERSION="1.0.0"
DEFAULT_DEBUG="false"
DEFAULT_JWT_ALGORITHM="HS256"
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES="30"
DEFAULT_PROMETHEUS_PUSH_INTERVAL_SECONDS="30"
DEFAULT_LOG_TIMEZONE="Asia/Seoul"
DEFAULT_NHN_STORAGE_AUTH_URL="https://api-identity-infrastructure.nhncloudservice.com/v2.0"
DEFAULT_NHN_STORAGE_CONTAINER="photo-container"
DEFAULT_NHN_STORAGE_URL="https://api-storage.nhncloudservice.com/v1"
DEFAULT_NHN_S3_ENDPOINT_URL="https://kr1-api-object-storage.nhncloudservice.com"
DEFAULT_NHN_S3_REGION_NAME="kr1"
DEFAULT_NHN_S3_PRESIGNED_URL_EXPIRE_SECONDS="3600"

# 필요한 환경 변수 export (주입 값 우선, 없으면 기본값, 계정/비밀은 빈 문자열)
export ENVIRONMENT="${ENVIRONMENT:-$DEFAULT_ENVIRONMENT}"
export APP_NAME="${APP_NAME:-$DEFAULT_APP_NAME}"
export APP_VERSION="${APP_VERSION:-$DEFAULT_APP_VERSION}"
export DEBUG="${DEBUG:-$DEFAULT_DEBUG}"
export DATABASE_URL="${DATABASE_URL:-}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-}"
export JWT_ALGORITHM="${JWT_ALGORITHM:-$DEFAULT_JWT_ALGORITHM}"
export ACCESS_TOKEN_EXPIRE_MINUTES="${ACCESS_TOKEN_EXPIRE_MINUTES:-$DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES}"
export INSTANCE_IP="${INSTANCE_IP:-$(hostname -I 2>/dev/null | awk '{print $1}' || echo '')}"
export LOKI_URL="${LOKI_URL:-$LOKI_URL_DEFAULT}"
export PROMETHEUS_PUSHGATEWAY_URL="${PROMETHEUS_PUSHGATEWAY_URL:-}"
export PROMETHEUS_PUSH_INTERVAL_SECONDS="${PROMETHEUS_PUSH_INTERVAL_SECONDS:-$DEFAULT_PROMETHEUS_PUSH_INTERVAL_SECONDS}"
export LOG_TIMEZONE="${LOG_TIMEZONE:-$DEFAULT_LOG_TIMEZONE}"
export LOG_DIR="${LOG_DIR:-}"
export NODE_NAME="${NODE_NAME:-}"
export NHN_STORAGE_IAM_USER="${NHN_STORAGE_IAM_USER:-}"
export NHN_STORAGE_IAM_PASSWORD="${NHN_STORAGE_IAM_PASSWORD:-}"
export NHN_STORAGE_USERNAME="${NHN_STORAGE_USERNAME:-}"
export NHN_STORAGE_PASSWORD="${NHN_STORAGE_PASSWORD:-}"
export NHN_STORAGE_PROJECT_ID="${NHN_STORAGE_PROJECT_ID:-}"
export NHN_STORAGE_TENANT_ID="${NHN_STORAGE_TENANT_ID:-}"
export NHN_STORAGE_AUTH_URL="${NHN_STORAGE_AUTH_URL:-$DEFAULT_NHN_STORAGE_AUTH_URL}"
export NHN_STORAGE_CONTAINER="${NHN_STORAGE_CONTAINER:-$DEFAULT_NHN_STORAGE_CONTAINER}"
export NHN_STORAGE_URL="${NHN_STORAGE_URL:-$DEFAULT_NHN_STORAGE_URL}"
export NHN_S3_ACCESS_KEY="${NHN_S3_ACCESS_KEY:-}"
export NHN_S3_SECRET_KEY="${NHN_S3_SECRET_KEY:-}"
export NHN_S3_ENDPOINT_URL="${NHN_S3_ENDPOINT_URL:-$DEFAULT_NHN_S3_ENDPOINT_URL}"
export NHN_S3_REGION_NAME="${NHN_S3_REGION_NAME:-$DEFAULT_NHN_S3_REGION_NAME}"
export NHN_S3_PRESIGNED_URL_EXPIRE_SECONDS="${NHN_S3_PRESIGNED_URL_EXPIRE_SECONDS:-$DEFAULT_NHN_S3_PRESIGNED_URL_EXPIRE_SECONDS}"
export NHN_STORAGE_TEMP_URL_KEY="${NHN_STORAGE_TEMP_URL_KEY:-}"
export NHN_CDN_DOMAIN="${NHN_CDN_DOMAIN:-}"
export NHN_CDN_APP_KEY="${NHN_CDN_APP_KEY:-}"
export NHN_CDN_SECRET_KEY="${NHN_CDN_SECRET_KEY:-}"
# 호환: 예전 이름 NHN_CDN_AUTH_KEY → NHN_CDN_ENCRYPT_KEY (app은 SECRET_KEY/ENCRYPT_KEY 사용)
export NHN_CDN_ENCRYPT_KEY="${NHN_CDN_ENCRYPT_KEY:-${NHN_CDN_AUTH_KEY:-}}"

usage() {
  echo "Usage: export VAR=value ... && $0"
  echo "       $0 --stdin        # read .env content from stdin (전체 내용 덮어씀)"
  echo "       $0 --restart-only # .env 건드리지 않고 서비스만 재시작"
  exit 0
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
fi

if [[ "${1:-}" == "--restart-only" ]]; then
  echo "Restart only (no .env write)"
elif [[ "${1:-}" == "--stdin" ]]; then
  sudo tee "$ENV_FILE" > /dev/null
  echo "Written .env from stdin to $ENV_FILE"
else
  # 현재 셸의 export 값 우선, 비어 있으면 기존 .env 값 유지 (배포 시 일부 변수만 넘겨도 나머지가 지워지지 않음)
  tmp=$(mktemp)
  for key in "${ENV_KEYS[@]}"; do
    val="${!key:-}"
    if [[ -z "$val" ]] && [[ -f "$ENV_FILE" ]]; then
      line=$(sudo grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1) || true
      if [[ -n "$line" ]]; then
        val="${line#*=}"
        val="${val#\"}"; val="${val%\"}"
        val="${val//\\\"/\"}"
      fi
    fi
    # LOKI_URL이 여전히 비어 있으면 기본값 (기존 .env에 LOKI_URL="" 있으면 병합 후에도 비어 있음)
    if [[ "$key" == "LOKI_URL" ]] && [[ -z "$val" ]]; then
      val="$LOKI_URL_DEFAULT"
    fi
    if [[ -n "$val" ]]; then
      val_escaped="${val//$'\n'/ }"
      val_escaped="${val_escaped//\"/\\\"}"
      echo "${key}=\"${val_escaped}\"" >> "$tmp"
    fi
  done
  if [[ -s "$tmp" ]]; then
    sudo cp -f "$tmp" "$ENV_FILE"
    echo "Written env vars to $ENV_FILE"
  else
    echo "No env vars to write. Export vars then run: export VAR=value ... && $0" >&2
    rm -f "$tmp"
    exit 1
  fi
  rm -f "$tmp"
fi

sudo systemctl restart "$SERVICE_NAME"
echo "Restarted $SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager || true

# Promtail은 /opt/photo-api/.env(LOKI_URL, INSTANCE_IP)를 사용하므로 .env 변경 후 재시작
if systemctl list-unit-files --full promtail.service 2>/dev/null | grep -q promtail.service; then
  sudo systemctl restart promtail
  echo "Restarted promtail (LOKI_URL/INSTANCE_IP 반영)"
fi
