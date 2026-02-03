#!/usr/bin/env bash
# Ubuntu 인스턴스 이미지 빌드 1단계: Python 3.11 설치
# 사용: sudo ./scripts/1-install-python.sh
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

echo "[1/4] 패키지 목록 업데이트..."
apt-get update -qq

echo "[2/4] 필수 패키지 설치 (curl, ca-certificates, build-essential)..."
apt-get install -y -qq \
  curl \
  ca-certificates \
  build-essential \
  libffi-dev \
  libssl-dev

echo "[3/4] deadsnakes PPA 추가 및 Python 3.11 설치..."
apt-get install -y -qq software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -qq
apt-get install -y -qq \
  python3.11 \
  python3.11-venv \
  python3.11-dev

echo "[4/4] python3.11 기본 심볼릭 확인..."
ln -sf /usr/bin/python3.11 /usr/bin/python3.11-run 2>/dev/null || true
python3.11 --version

echo "Python 3.11 설치 완료."
