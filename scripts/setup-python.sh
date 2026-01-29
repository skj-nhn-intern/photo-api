#!/bin/bash

# Python 환경 설정 스크립트 (Ubuntu)
# NHN Cloud Deploy User Command용
# 사용법: sudo ./setup-python.sh

set -e

echo "========================================"
echo "Python 환경 설정 스크립트"
echo "========================================"
echo ""

# 1. Python 3.11 설치 확인 및 설치
echo "[1/3] Python 3.11 설치 확인 중..."
if ! command -v python3.11 &> /dev/null; then
    echo "Python 3.11이 설치되어 있지 않습니다. 설치를 시작합니다..."
    
    # Ubuntu
    if command -v apt-get &> /dev/null; then
        # 저장소 업데이트
        apt-get update
        
        # 필수 패키지 설치
        apt-get install -y software-properties-common
        
        # deadsnakes PPA 추가 (Ubuntu용 Python 3.11)
        add-apt-repository -y ppa:deadsnakes/ppa
        
        # 저장소 업데이트
        apt-get update
        
        # Python 3.11 설치
        apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip
    else
        echo "ERROR: 지원하지 않는 패키지 관리자입니다. Python 3.11을 수동으로 설치해주세요."
        exit 1
    fi
else
    echo "OK: Python 3.11이 이미 설치되어 있습니다."
fi

PYTHON_VERSION=$(python3.11 --version)
echo "OK: Python 버전: $PYTHON_VERSION"

# 2. 시스템 의존성 설치
echo "[2/3] 시스템 의존성 설치 중..."

if command -v apt-get &> /dev/null; then
    # 저장소 업데이트
    apt-get update
    
    apt-get install -y \
        gcc \
        g++ \
        make \
        libpq-dev \
        build-essential \
        curl \
        unzip
else
    echo "ERROR: 지원하지 않는 패키지 관리자입니다."
    exit 1
fi

echo "OK: 시스템 의존성 설치 완료"

# 3. pip 업그레이드
echo "[3/3] pip 업그레이드 중..."
python3.11 -m pip install --upgrade pip setuptools wheel

echo "OK: pip 업그레이드 완료"

echo ""
echo "========================================"
echo "Python 환경 설정 완료!"
echo "========================================"
echo ""
echo "설치된 Python 버전:"
python3.11 --version
echo ""
echo "설치된 pip 버전:"
python3.11 -m pip --version
