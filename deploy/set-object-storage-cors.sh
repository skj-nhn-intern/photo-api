#!/usr/bin/env bash
#
# NHN Cloud Object Storage 컨테이너에 CORS 권한 설정 (Swift API).
# Temp URL(PUT)로 브라우저에서 직접 업로드할 때 OPTIONS preflight가 통과하도록 합니다.
# IAM 사용자/비밀번호로 Identity API를 호출해 토큰을 발급한 뒤 CORS를 설정합니다.
#
# 사용 방법:
#   export OS_TENANT_ID="your-tenant-id"
#   export NHN_STORAGE_IAM_USER="your-iam-user"
#   export NHN_STORAGE_IAM_PASSWORD="your-password"
#   ./deploy/set-object-storage-cors.sh
#
# 선택: Temp URL Key 동시 설정 — export NHN_STORAGE_TEMP_URL_KEY="your-secret-key"
# 선택: CORS 오리진 제한 — export CORS_ORIGIN="https://your-frontend.com"
#
# 요구: curl, jq 또는 python3 (JSON 파싱용)
set -euo pipefail

# 기본값
OS_ENDPOINT="${OS_ENDPOINT:-https://kr1-api-object-storage.nhncloudservice.com}"
OS_TENANT_ID="${OS_TENANT_ID:-${NHN_STORAGE_TENANT_ID:-${NHN_STORAGE_PROJECT_ID:-}}}"
OS_CONTAINER="${OS_CONTAINER:-photo}"

NHN_STORAGE_AUTH_URL="${NHN_STORAGE_AUTH_URL:-https://api-identity-infrastructure.nhncloudservice.com/v2.0}"
NHN_STORAGE_IAM_USER="${NHN_STORAGE_IAM_USER:-${NHN_STORAGE_USERNAME:-}}"
NHN_STORAGE_IAM_PASSWORD="${NHN_STORAGE_IAM_PASSWORD:-${NHN_STORAGE_PASSWORD:-}}"

CORS_ORIGIN="${CORS_ORIGIN:-*}"
TEMP_URL_KEY="${NHN_STORAGE_TEMP_URL_KEY:-iamsecret113}"

# 필수: IAM 인증 정보
export OS_TENANT_ID NHN_STORAGE_IAM_USER NHN_STORAGE_IAM_PASSWORD
if [[ -z "$OS_TENANT_ID" ]] || [[ -z "$NHN_STORAGE_IAM_USER" ]] || [[ -z "$NHN_STORAGE_IAM_PASSWORD" ]]; then
  echo "::error::다음 환경 변수를 설정하세요:"
  echo "  OS_TENANT_ID (또는 NHN_STORAGE_TENANT_ID)"
  echo "  NHN_STORAGE_IAM_USER (또는 NHN_STORAGE_USERNAME)"
  echo "  NHN_STORAGE_IAM_PASSWORD (또는 NHN_STORAGE_PASSWORD)"
  exit 1
fi

# IAM 토큰 발급
AUTH_URL="${NHN_STORAGE_AUTH_URL%/}"
[[ "$AUTH_URL" == */v3 ]] && AUTH_URL="${AUTH_URL%/v3}/v2.0"
AUTH_URL="${AUTH_URL}/tokens"

echo "🔐 IAM 토큰 발급 중..."
if command -v jq &>/dev/null; then
  AUTH_JSON=$(jq -n \
    --arg tid "$OS_TENANT_ID" \
    --arg user "$NHN_STORAGE_IAM_USER" \
    --arg pass "$NHN_STORAGE_IAM_PASSWORD" \
    '{auth:{tenantId:$tid,passwordCredentials:{username:$user,password:$pass}}}')
else
  AUTH_JSON=$(python3 -c "
import json, os
print(json.dumps({
    'auth': {
        'tenantId': os.environ.get('OS_TENANT_ID', ''),
        'passwordCredentials': {
            'username': os.environ.get('NHN_STORAGE_IAM_USER', ''),
            'password': os.environ.get('NHN_STORAGE_IAM_PASSWORD', '')
        }
    }
}))
" 2>/dev/null)
fi
if [[ -z "$AUTH_JSON" ]]; then
  echo "::error::인증 JSON 생성 실패. jq 또는 python3를 확인하세요."
  exit 1
fi

AUTH_RESP=$(curl -s -w "\n%{http_code}" -X POST "${AUTH_URL}" \
  -H "Content-Type: application/json" \
  -d "$AUTH_JSON")

HTTP_BODY=$(echo "$AUTH_RESP" | sed '$d')
HTTP_CODE=$(echo "$AUTH_RESP" | tail -n 1)

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "::error::IAM 토큰 발급 실패 (HTTP $HTTP_CODE)"
  echo "$HTTP_BODY" | head -20
  exit 1
fi

if command -v jq &>/dev/null; then
  X_AUTH_TOKEN=$(echo "$HTTP_BODY" | jq -r '.access.token.id // empty')
  [[ -z "$OS_TENANT_ID" ]] && OS_TENANT_ID=$(echo "$HTTP_BODY" | jq -r '.access.token.tenant.id // empty')
else
  X_AUTH_TOKEN=$(echo "$HTTP_BODY" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('access', {}).get('token', {}).get('id', '') or '')
except Exception:
    sys.exit(1)
" 2>/dev/null)
  if [[ -z "$OS_TENANT_ID" ]]; then
    OS_TENANT_ID=$(echo "$HTTP_BODY" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('access', {}).get('token', {}).get('tenant', {}).get('id', '') or '')
except Exception:
    pass
" 2>/dev/null)
  fi
fi

if [[ -z "$X_AUTH_TOKEN" ]]; then
  echo "::error::응답에서 토큰을 찾을 수 없습니다. jq 또는 python3로 JSON 파싱이 필요합니다."
  exit 1
fi
echo "✅ 토큰 발급 완료"

CONTAINER_URL="${OS_ENDPOINT%/}/v1/AUTH_${OS_TENANT_ID}/${OS_CONTAINER}"

echo "컨테이너 URL: $CONTAINER_URL"
echo "CORS Allow-Origin: $CORS_ORIGIN"

# Swift CORS 메타데이터 (OpenStack Swift 호환)
# 참조: https://docs.openstack.org/swift/latest/cors.html
CORS_HEADERS=(
  -H "X-Auth-Token: ${X_AUTH_TOKEN}"
  -H "X-Container-Meta-Access-Control-Allow-Origin: ${CORS_ORIGIN}"
  -H "X-Container-Meta-Access-Control-Max-Age: 3600"
  -H "X-Container-Meta-Access-Control-Expose-Headers: etag x-timestamp content-length"
)

# Temp URL Key 동시 설정 (선택)
if [[ -n "$TEMP_URL_KEY" ]]; then
  CORS_HEADERS+=( -H "X-Container-Meta-Temp-URL-Key: ${TEMP_URL_KEY}" )
  echo "Temp URL Key 설정 포함"
fi

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${CORS_HEADERS[@]}" "$CONTAINER_URL")

if [[ "$HTTP_CODE" =~ ^(2[0-9][0-9]|204)$ ]]; then
  echo "✅ CORS 설정 완료 (HTTP $HTTP_CODE)"
else
  echo "❌ CORS 설정 실패 (HTTP $HTTP_CODE)"
  echo "응답 확인:"
  curl -s -w "\n" -X POST "${CORS_HEADERS[@]}" "$CONTAINER_URL" || true
  exit 1
fi
