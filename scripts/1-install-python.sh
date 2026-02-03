#!/bin/bash
# 1. Python 3.11 및 시스템 의존성 설치
# 사용법: sudo ./1-install-python.sh

set -e

# apt 잠금이 풀릴 때까지 대기 (다른 apt-get/dpkg 프로세스가 끝날 때까지)
wait_for_apt_lock() {
    local max_wait=300  # 최대 5분
    local waited=0

    while [ $waited -lt $max_wait ]; do
        if pgrep -x apt-get &>/dev/null || pgrep -x dpkg &>/dev/null; then
            echo "apt/dpkg 잠금 대기 중... (다른 설치가 진행 중, ${waited}s/${max_wait}s)"
            sleep 5
            waited=$((waited + 5))
        else
            return 0
        fi
    done
    echo "오류: apt 잠금이 ${max_wait}초 내에 해제되지 않았습니다."
    echo "다른 터미널에서 'sudo apt-get' 또는 자동 업데이트가 끝날 때까지 기다린 뒤 다시 시도하세요."
    echo "이전 프로세스가 비정상 종료되었다면: sudo rm -f /var/lib/apt/lists/lock /var/lib/dpkg/lock* 후 재시도."
    exit 1
}

# apt 사용 시 잠금 대기 후 실행
run_apt_update() {
    wait_for_apt_lock
    sudo apt-get update
}
run_apt_install() {
    wait_for_apt_lock
    sudo apt-get install -y "$@"
}

echo "========================================"
echo "[1/4] Python 3.11 설치"
echo "========================================"
echo ""

echo "Python 3.11 설치 확인 중..."
if ! command -v python3.11 &> /dev/null; then
    echo "Python 3.11이 설치되어 있지 않습니다."
    echo "Python 3.11을 설치합니다..."

    if command -v apt-get &> /dev/null; then
        run_apt_update
        run_apt_install software-properties-common
        sudo add-apt-repository -y ppa:deadsnakes/ppa
        run_apt_update
        run_apt_install python3.11 python3.11-venv python3.11-dev python3-pip
    elif command -v yum &> /dev/null; then
        sudo yum install -y python311 python311-pip python311-devel
    else
        echo "지원하지 않는 패키지 관리자입니다. Python 3.11을 수동으로 설치해주세요."
        exit 1
    fi
fi

PYTHON_VERSION=$(python3.11 --version)
echo "Python 설치됨: $PYTHON_VERSION"
echo ""

echo "시스템 의존성 설치 중..."
if command -v apt-get &> /dev/null; then
    run_apt_update
    run_apt_install gcc g++ make libpq-dev build-essential
elif command -v yum &> /dev/null; then
    sudo yum groupinstall -y "Development Tools"
    sudo yum install -y postgresql-devel
fi
echo "시스템 의존성 설치 완료"
echo ""
echo "========================================"
echo "[1/4] 완료. 다음: sudo ./2-setup-photo-api.sh"
echo "========================================"
