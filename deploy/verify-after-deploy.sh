#!/usr/bin/env bash
#
# 배포 후 실행 검증 스크립트.
# apply-env-and-restart.sh 실행 직후, 같은 서버 또는 원격에서 이 스크립트로
# photo-api 서비스·헬스·API 응답을 확인합니다.
#
# 사용 예:
#   로컬(같은 서버): sudo /opt/photo-api/deploy/verify-after-deploy.sh
#   원격:            BASE_URL=http://서버IP:8000 ./verify-after-deploy.sh
#
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-photo-api}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
MAX_WAIT="${MAX_WAIT:-30}"   # 헬스 체크 재시도 최대 대기 시간(초)
CURL_TIMEOUT="${CURL_TIMEOUT:-10}"

# BASE_URL에서 호스트/포트만 추출 (표준 출력용)
url_display="$BASE_URL"

ok()  { echo "  ✅ $*"; }
fail() { echo "  ❌ $*" >&2; }
warn() { echo "  ⚠️  $*"; }

# 1) systemd 서비스 상태 (로컬에서만 의미 있음)
check_service() {
  echo "1. 서비스 상태 ($SERVICE_NAME)"
  if ! command -v systemctl &>/dev/null; then
    warn "systemctl 없음, 서비스 검사 생략"
    return 0
  fi
  if ! systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    fail "서비스가 active가 아님. sudo systemctl status $SERVICE_NAME 확인"
    return 1
  fi
  ok "서비스 active"
  return 0
}

# 2) 헬스 엔드포인트 200 + body에 healthy (경로는 /health/ — trailing slash 필수, 미사용 시 307 리다이렉트)
check_health() {
  echo "2. 헬스 체크 ($url_display/health/)"
  local waited=0
  local code body
  while true; do
    code=$(curl -s -o /tmp/photo-api-health-$$.json -w "%{http_code}" --connect-timeout 5 --max-time "$CURL_TIMEOUT" "$BASE_URL/health/" 2>/dev/null || echo "000")
    body=$(cat /tmp/photo-api-health-$$.json 2>/dev/null || true)
    rm -f /tmp/photo-api-health-$$.json

    if [[ "$code" == "200" ]] && echo "$body" | grep -q "healthy"; then
      ok "HTTP $code, body: $body"
      return 0
    fi
    if [[ "$waited" -ge "$MAX_WAIT" ]]; then
      fail "헬스 실패 (HTTP $code, body: ${body:0:80})"
      if [[ "$code" == "000" ]]; then
        echo "    연결 불가(Connection refused/타임아웃). 아래 진단 참고." >&2
      fi
      return 1
    fi
    echo "    대기 중... (${waited}s/${MAX_WAIT}s)"
    sleep 2
    waited=$((waited + 2))
  done
}

# 3) 루트 API 응답 (이름·버전)
check_root() {
  echo "3. 루트 API ($url_display/)"
  local code body
  code=$(curl -s -o /tmp/photo-api-root-$$.json -w "%{http_code}" --connect-timeout 5 --max-time "$CURL_TIMEOUT" "$BASE_URL/" 2>/dev/null || echo "000")
  body=$(cat /tmp/photo-api-root-$$.json 2>/dev/null || true)
  rm -f /tmp/photo-api-root-$$.json

  if [[ "$code" != "200" ]]; then
    fail "HTTP $code"
    return 1
  fi
  if echo "$body" | grep -qE '"name"|"version"'; then
    ok "HTTP $code — $body"
  else
    warn "HTTP $code — 응답에 name/version 없음: $body"
  fi
  return 0
}

# 4) 메트릭 엔드포인트 (선택)
check_metrics() {
  echo "4. 메트릭 ($url_display/metrics)"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time "$CURL_TIMEOUT" "$BASE_URL/metrics" 2>/dev/null || echo "000")
  if [[ "$code" == "200" ]]; then
    ok "HTTP $code"
  else
    warn "HTTP $code (메트릭 비활성화일 수 있음)"
  fi
  return 0
}

# 실행
main() {
  echo "=== 배포 검증: $url_display ==="
  failed=0
  check_service || failed=1
  check_health  || failed=1
  check_root    || failed=1
  check_metrics || true

  echo ""
  if [[ $failed -eq 0 ]]; then
    echo "✅ 배포 검증 완료."
    exit 0
  else
    echo "❌ 배포 검증 실패. 위 항목을 확인하세요."
    echo ""
    echo "--- 진단 결과 ---"
    echo ""
    echo "[ systemctl status $SERVICE_NAME ]"
    (systemctl status "$SERVICE_NAME" --no-pager 2>&1 || true)
    echo ""
    echo "[ journalctl -u $SERVICE_NAME -n 30 --no-pager ]"
    (journalctl -u "$SERVICE_NAME" -n 30 --no-pager 2>&1 || true)
    echo ""
    if command -v ss &>/dev/null; then
      echo "[ ss -tlnp | grep 8000 ]"
      (ss -tlnp 2>/dev/null | grep 8000) || echo "(8000 포트 리스닝 없음)"
    fi
    echo ""
    echo "[ curl -v $BASE_URL/health/ (timeout 5s) ]"
    (curl -v --connect-timeout 5 --max-time 5 "$BASE_URL/health/" 2>&1 || true)
    echo ""
    echo "--- 진단 끝 ---"
    exit 1
  fi
}

main "$@"
