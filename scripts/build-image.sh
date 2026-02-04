#!/usr/bin/env bash
# Ubuntu 인스턴스 이미지 빌드: 1~4단계 순차 실행
# Packer/이미지 빌드 VM에서 실행하거나, 새 Ubuntu 인스턴스에서 한 번에 설정할 때 사용
# 사용: sudo ./scripts/build-image.sh!
# 환경변수: PHOTO_API_SOURCE, PROMTAIL_VERSION, TELEGRAF_VERSION, LOKI_URL, INFLUX_URL, INFLUX_TOKEN
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
# 실행 권한 없이도 동작하도록 chmod (clone 후 바로 실행 가능)
chmod +x 1-install-python.sh 2-setup-photo-api.sh 3-setup-promtail.sh 4-setup-telegraf.sh run-services.sh 2>/dev/null || true

echo "=== 1/4 Python 3.11 설치 ==="
bash "$SCRIPT_DIR/1-install-python.sh"

echo "=== 2/4 photo-api systemd 패키징 ==="
bash "$SCRIPT_DIR/2-setup-photo-api.sh"

echo "=== 3/4 Promtail 설치 및 구성 ==="
bash "$SCRIPT_DIR/3-setup-promtail.sh"

echo "=== 4/4 Telegraf 설치 및 구성 ==="
bash "$SCRIPT_DIR/4-setup-telegraf.sh"

echo "=== 이미지 빌드 스크립트 완료 ==="
echo "서비스 시작: systemctl start photo-api promtail telegraf"
echo "상태 확인: systemctl status photo-api promtail telegraf"
