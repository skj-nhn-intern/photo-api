#!/usr/bin/env bash
# photo-api 스택 systemctl 실행 스크립트 (인스턴스 내에서 사용)
# 이미지에서는 서비스가 중지된 상태; 부팅 시 enable 되어 있으면 자동 기동됨.
# 수동 제어: sudo /opt/photo-api/scripts/run-services.sh start|stop|restart|status
set -euo pipefail

SERVICES="photo-api promtail telegraf"

case "${1:-status}" in
  start)
    systemctl start $SERVICES
    echo "Started: $SERVICES"
    ;;
  stop)
    systemctl stop $SERVICES
    echo "Stopped: $SERVICES"
    ;;
  restart)
    systemctl restart $SERVICES
    echo "Restarted: $SERVICES"
    ;;
  status)
    systemctl status $SERVICES --no-pager || true
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}" >&2
    exit 1
    ;;
esac
