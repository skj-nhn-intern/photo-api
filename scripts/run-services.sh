#!/bin/bash
#
# build-image.sh 로 구성된 인스턴스에서 서비스를 기동하는 스크립트
# 사용법: sudo ./scripts/run-services.sh
#
# 기동 서비스: photo-api, promtail, telegraf

set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "root 권한이 필요합니다. sudo $0 로 실행하세요."
    exit 1
fi

echo "=========================================="
echo "인스턴스 서비스 기동"
echo "=========================================="

systemctl start photo-api
echo "  photo-api started"

systemctl start promtail
echo "  promtail started"

systemctl start telegraf
echo "  telegraf started"

echo ""
echo "상태 확인:"
systemctl is-active --quiet photo-api  && echo "  photo-api: active" || echo "  photo-api: failed"
systemctl is-active --quiet promtail   && echo "  promtail:  active" || echo "  promtail:  failed"
systemctl is-active --quiet telegraf  && echo "  telegraf:  active" || echo "  telegraf:  failed"
echo ""
echo "자세한 상태: systemctl status photo-api promtail telegraf"
