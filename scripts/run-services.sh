#!/bin/bash
# photo-api, promtail, telegraf 시작 (실행 중이면 재시작)
# 사용법: sudo ./scripts/run-services.sh

set -e

SERVICES="photo-api promtail telegraf"

if [ "$(id -u)" -ne 0 ]; then
  echo "root 권한이 필요합니다. sudo $0"
  exit 1
fi

for svc in $SERVICES; do
  systemctl restart "$svc"
  echo "  $svc: $(systemctl is-active "$svc")"
done
