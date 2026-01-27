#!/bin/bash

# Photo API 로그 확인 스크립트
# 사용법: ./view-logs.sh [옵션]

SERVICE_NAME="photo-api"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

show_help() {
    echo "Photo API 로그 확인 스크립트"
    echo ""
    echo "사용법: $0 [옵션]"
    echo ""
    echo "옵션:"
    echo "  -f, --follow      실시간 로그 확인 (tail -f)"
    echo "  -n, --lines N     최근 N줄만 표시 (기본값: 50)"
    echo "  -e, --error       에러 로그만 표시"
    echo "  -s, --since TIME  특정 시간 이후 로그 (예: '1 hour ago', '10 minutes ago')"
    echo "  -t, --today       오늘 로그만 표시"
    echo "  -h, --help        도움말 표시"
    echo ""
    echo "예시:"
    echo "  $0 -f              # 실시간 로그 확인"
    echo "  $0 -n 100          # 최근 100줄 표시"
    echo "  $0 -e              # 에러 로그만 표시"
    echo "  $0 -s '1 hour ago' # 1시간 전부터 로그"
    echo "  $0 -t              # 오늘 로그만 표시"
}

# 기본값
FOLLOW=false
LINES=50
ERROR_ONLY=false
SINCE=""
TODAY=false

# 옵션 파싱
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--follow)
            FOLLOW=true
            shift
            ;;
        -n|--lines)
            LINES="$2"
            shift 2
            ;;
        -e|--error)
            ERROR_ONLY=true
            shift
            ;;
        -s|--since)
            SINCE="$2"
            shift 2
            ;;
        -t|--today)
            TODAY=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}알 수 없는 옵션: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# journalctl 명령어 구성
CMD="sudo journalctl -u $SERVICE_NAME"

# 옵션 추가
if [ "$FOLLOW" = true ]; then
    CMD="$CMD -f"
elif [ "$TODAY" = true ]; then
    CMD="$CMD --since today"
elif [ -n "$SINCE" ]; then
    CMD="$CMD --since '$SINCE'"
else
    CMD="$CMD -n $LINES"
fi

# 에러만 표시
if [ "$ERROR_ONLY" = true ]; then
    CMD="$CMD -p err"
fi

# 색상 출력 추가
CMD="$CMD --no-pager"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Photo API 로그 확인${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 명령어 실행
eval $CMD
