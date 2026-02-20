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
  NHN_STORAGE_TEMP_URL_KEY
  NHN_CDN_SECRET_KEY
  NHN_CDN_ENCRYPT_KEY
)

# 필요한 환경 변수 export (NHN Deploy에서 주입한 값이 있으면 사용)
export ENVIRONMENT="${ENVIRONMENT:-PRODUCTION}"
export APP_NAME="${APP_NAME:-kr1-api}"
export APP_VERSION="${APP_VERSION:-1.0.0}"
export DEBUG="${DEBUG:-true}"
export DATABASE_URL="${DATABASE_URL:-mysql+asyncmy://nhn-intern:intern%211@192.168.3.63:13306/photo_api}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-secret-jwt}"
export JWT_ALGORITHM="${JWT_ALGORITHM:-HS256}"
export ACCESS_TOKEN_EXPIRE_MINUTES="${ACCESS_TOKEN_EXPIRE_MINUTES:-30}"
export INSTANCE_IP="${INSTANCE_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
export LOKI_URL="${LOKI_URL:-http://192.168.4.73:3100}"
export PROMETHEUS_PUSHGATEWAY_URL="${PROMETHEUS_PUSHGATEWAY_URL:-http://192.168.4.73:9091}"
export PROMETHEUS_PUSH_INTERVAL_SECONDS="${PROMETHEUS_PUSH_INTERVAL_SECONDS:-30}"
export NHN_STORAGE_IAM_USER="${NHN_STORAGE_IAM_USER:-sookju@nhn.com}"
export NHN_STORAGE_IAM_PASSWORD="${NHN_STORAGE_IAM_PASSWORD:-ugo!girl113!}"
export NHN_STORAGE_PROJECT_ID="${NHN_STORAGE_PROJECT_ID:-nCZNJgGY}"
export NHN_STORAGE_TENANT_ID="${NHN_STORAGE_TENANT_ID:-5883ff5244d6421e964eb56f20f93e76}"
export NHN_STORAGE_AUTH_URL="${NHN_STORAGE_AUTH_URL:-https://api-identity-infrastructure.nhncloudservice.com/v2.0}"
export NHN_STORAGE_CONTAINER="${NHN_STORAGE_CONTAINER:-photo}"
export NHN_STORAGE_URL="${NHN_STORAGE_URL:-https://kr1-api-object-storage.nhncloudservice.com/v1/AUTH_5883ff5244d6421e964eb56f20f93e76/photo}"
export NHN_S3_ACCESS_KEY="${NHN_S3_ACCESS_KEY:-5447d231761b447a845140a64ae98852}"
export NHN_S3_SECRET_KEY="${NHN_S3_SECRET_KEY:-2f67714f8d3547b1a960a38501fc56ae}"
export NHN_S3_ENDPOINT_URL="${NHN_S3_ENDPOINT_URL:-https://kr1-api-object-storage.nhncloudservice.com/v1/AUTH_5883ff5244d6421e964eb56f20f93e76/photo}"
export NHN_S3_REGION_NAME="${NHN_S3_REGION_NAME:-kr1}"
export NHN_S3_PRESIGNED_URL_EXPIRE_SECONDS="${NHN_S3_PRESIGNED_URL_EXPIRE_SECONDS:-3600}"
export NHN_CDN_DOMAIN="${NHN_CDN_DOMAIN:-rlbyozuin.toastcdn.net}"
export NHN_CDN_APP_KEY="${NHN_CDN_APP_KEY:-FIv6zNJWGTYHFVCm}"
export NHN_CDN_AUTH_KEY="${NHN_CDN_AUTH_KEY:-btj8ojjsIvMrkaWpaJA62vpuoEMKPXui}"
export NHN_OBJECT_STORAGE_ENDPOINT="${NHN_OBJECT_STORAGE_ENDPOINT:-https://kr1-api-object-storage.nhncloudservice.com/v1/AUTH_5883ff5244d6421e964eb56f20f93e76/photo}"
export NHN_OBJECT_STORAGE_ACCESS_KEY="${NHN_OBJECT_STORAGE_ACCESS_KEY:-5447d231761b447a845140a64ae98852}"
export NHN_OBJECT_STORAGE_SECRET_KEY="${NHN_OBJECT_STORAGE_SECRET_KEY:-2f67714f8d3547b1a960a38501fc56ae}"
export NHN_STORAGE_TEMP_URL_KEY="${NHN_STORAGE_TEMP_URL_KEY:-do113!dong72gru}"
export NHN_CDN_ENCRYPT_KEY="${NHN_CDN_ENCRYPT_KEY:-btj8ojjsIvMrkaWpaJA62vpuoEMKPXui}"
export NHN_CDN_SECRET_KEY="${NHN_CDN_SECRET_KEY:-btj8ojjsIvMrkaWpaJA62vpuoEMKPXui}"

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

# Promtail은 /opt/photo-api/.env(LOKI_URL, INSTANCE_IP)를 사용하므로 .env 변경 후 재시작
if systemctl list-unit-files --full promtail.service 2>/dev/null | grep -q promtail.service; then
  sudo systemctl restart promtail
  echo "Restarted promtail (LOKI_URL/INSTANCE_IP 반영)"
fi

journalctl -u promtail --no-pager -n 20 || true
sudo grep -E "^(LOKI_URL|NHN_CDN)" "$ENV_FILE" 2>/dev/null || true
systemctl status promtail --no-pager || true
