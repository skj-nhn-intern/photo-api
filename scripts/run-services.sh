#!/bin/bash
#
# 서비스 재설치 스크립트: 기존 서비스 삭제 후 다시 빌드
#
# 사용법:
#   export LOKI_URL=... INFLUX_URL=... INFLUX_TOKEN=... INFLUX_ORG=... INFLUX_BUCKET=...
#   sudo -E ./scripts/run-services.sh
#
# 동작:
#   1. 기존 photo-api, promtail, telegraf 서비스 중지 및 삭제
#   2. build-image.sh 실행 (재설치)
#   3. 서비스 시작

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICES="photo-api promtail telegraf"

if [ "$(id -u)" -ne 0 ]; then
    echo "root 권한이 필요합니다. sudo -E $0 로 실행하세요."
    exit 1
fi

echo "=========================================="
echo "1. 기존 서비스 삭제"
echo "=========================================="

for svc in $SERVICES; do
  if systemctl list-unit-files | grep -q "^${svc}.service"; then
    echo "  $svc 서비스 발견 → 중지 및 삭제"
    systemctl stop "$svc" 2>/dev/null || true
    systemctl disable "$svc" 2>/dev/null || true
    rm -f "/etc/systemd/system/${svc}.service"
  else
    echo "  $svc 서비스 없음"
  fi
done

systemctl daemon-reload
echo "  systemd 리로드 완료"

echo ""
echo "=========================================="
echo "2. 서비스 재설치 (build-image.sh)"
echo "=========================================="

bash "$SCRIPT_DIR/build-image.sh"

echo ""
echo "=========================================="
echo "3. 서비스 시작"
echo "=========================================="

for svc in $SERVICES; do
  systemctl start "$svc"
  echo "  $svc started"
done

echo ""
echo "상태 확인:"
for svc in $SERVICES; do
  if systemctl is-active --quiet "$svc"; then
    echo "  $svc: active"
  else
    echo "  $svc: failed"
  fi
done

echo ""
echo "자세한 상태: systemctl status $SERVICES"
echo "환경변수 변경: /etc/default/photo-api 수정 후 systemctl restart $SERVICES"
