#!/usr/bin/env bash
#
# NHN Deploy User Command용: 환경 변수 반영 후 photo-api 서비스 재시작.
# 스크립트에서 앱용 환경 변수를 export 한 뒤 .env에 씁니다.
#
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-photo-api}"
ENV_FILE="${ENV_FILE:-/opt/photo-api/.env}"

# 앱에서 참조하는 환경 변수 이름 (필요 시 추가)
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
  NHN_STORAGE_IAM_USER
  NHN_STORAGE_IAM_PASSWORD
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
  NHN_CDN_DOMAIN
  NHN_CDN_APP_KEY
  NHN_CDN_AUTH_KEY
  NHN_OBJECT_STORAGE_ENDPOINT
  NHN_OBJECT_STORAGE_ACCESS_KEY
  NHN_OBJECT_STORAGE_SECRET_KEY
)

# 필요한 환경 변수 export (NHN Deploy에서 주입한 값이 있으면 사용)
export ENVIRONMENT="${ENVIRONMENT:-}"
export APP_NAME="${APP_NAME:-}"
export APP_VERSION="${APP_VERSION:-}"
export DEBUG="${DEBUG:-}"
export DATABASE_URL="${DATABASE_URL:-}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-}"
export JWT_ALGORITHM="${JWT_ALGORITHM:-}"
export ACCESS_TOKEN_EXPIRE_MINUTES="${ACCESS_TOKEN_EXPIRE_MINUTES:-}"
export INSTANCE_IP="${INSTANCE_IP:-}"
export LOKI_URL="${LOKI_URL:-}"
export PROMETHEUS_PUSHGATEWAY_URL="${PROMETHEUS_PUSHGATEWAY_URL:-}"
export PROMETHEUS_PUSH_INTERVAL_SECONDS="${PROMETHEUS_PUSH_INTERVAL_SECONDS:-}"
export NHN_STORAGE_IAM_USER="${NHN_STORAGE_IAM_USER:-}"
export NHN_STORAGE_IAM_PASSWORD="${NHN_STORAGE_IAM_PASSWORD:-}"
export NHN_STORAGE_PROJECT_ID="${NHN_STORAGE_PROJECT_ID:-}"
export NHN_STORAGE_TENANT_ID="${NHN_STORAGE_TENANT_ID:-}"
export NHN_STORAGE_AUTH_URL="${NHN_STORAGE_AUTH_URL:-}"
export NHN_STORAGE_CONTAINER="${NHN_STORAGE_CONTAINER:-}"
export NHN_STORAGE_URL="${NHN_STORAGE_URL:-}"
export NHN_S3_ACCESS_KEY="${NHN_S3_ACCESS_KEY:-}"
export NHN_S3_SECRET_KEY="${NHN_S3_SECRET_KEY:-}"
export NHN_S3_ENDPOINT_URL="${NHN_S3_ENDPOINT_URL:-}"
export NHN_S3_REGION_NAME="${NHN_S3_REGION_NAME:-}"
export NHN_S3_PRESIGNED_URL_EXPIRE_SECONDS="${NHN_S3_PRESIGNED_URL_EXPIRE_SECONDS:-}"
export NHN_CDN_DOMAIN="${NHN_CDN_DOMAIN:-}"
export NHN_CDN_APP_KEY="${NHN_CDN_APP_KEY:-}"
export NHN_CDN_AUTH_KEY="${NHN_CDN_AUTH_KEY:-}"
export NHN_OBJECT_STORAGE_ENDPOINT="${NHN_OBJECT_STORAGE_ENDPOINT:-}"
export NHN_OBJECT_STORAGE_ACCESS_KEY="${NHN_OBJECT_STORAGE_ACCESS_KEY:-}"
export NHN_OBJECT_STORAGE_SECRET_KEY="${NHN_OBJECT_STORAGE_SECRET_KEY:-}"

usage() {
  echo "Usage: export VAR=value ... && $0"
  echo "       $0 --stdin   # read .env content from stdin"
  exit 0
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
fi

if [[ "${1:-}" == "--stdin" ]]; then
  sudo tee "$ENV_FILE" > /dev/null
  echo "Written .env from stdin to $ENV_FILE"
else
  # 현재 셸에서 export 된 환경 변수 중 앱 관련만 골라 .env에 씀
  tmp=$(mktemp)
  for key in "${ENV_KEYS[@]}"; do
    val="${!key:-}"
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
