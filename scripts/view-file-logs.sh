#!/bin/bash

# Photo API 파일 로그 확인 스크립트
# Promtail이 Loki로 전송하는 파일 로그 확인

LOG_DIR="/var/log/photo-api"
SERVICE_NAME="photo-api"

show_help() {
    echo "Photo API 파일 로그 확인 스크립트 (Promtail → Loki)"
    echo ""
    echo "사용법: $0 [옵션] [로그 타입]"
    echo ""
    echo "로그 타입:"
    echo "  app      애플리케이션 로그 (기본값)"
    echo "  error    에러 로그"
    echo "  all      모든 로그"
    echo ""
    echo "옵션:"
    echo "  -f, --follow      실시간 로그 확인 (tail -f)"
    echo "  -n, --lines N     최근 N줄만 표시 (기본값: 50)"
    echo "  -h, --help        도움말 표시"
    echo ""
    echo "예시:"
    echo "  $0 -f app         # 애플리케이션 로그 실시간 확인"
    echo "  $0 -f error       # 에러 로그 실시간 확인"
    echo "  $0 -n 100 app     # 최근 100줄 애플리케이션 로그"
}

# 기본값
FOLLOW=false
LINES=50
LOG_TYPE="app"

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
        -h|--help)
            show_help
            exit 0
            ;;
        app|error|all)
            LOG_TYPE="$1"
            shift
            ;;
        *)
            echo "알 수 없는 옵션: $1"
            show_help
            exit 1
            ;;
    esac
done

# 로그 파일 선택
case $LOG_TYPE in
    app)
        LOG_FILE="$LOG_DIR/app.log"
        LOG_NAME="애플리케이션"
        ;;
    error)
        LOG_FILE="$LOG_DIR/error.log"
        LOG_NAME="에러"
        ;;
    all)
        LOG_FILE="$LOG_DIR/*.log"
        LOG_NAME="모든"
        ;;
esac

# 파일 존재 확인
if [ "$LOG_TYPE" != "all" ] && [ ! -f "$LOG_FILE" ]; then
    echo "로그 파일이 없습니다: $LOG_FILE"
    echo "서비스가 시작되면 로그 파일이 생성됩니다."
    exit 1
fi

echo "========================================"
echo "Photo API ${LOG_NAME} 로그 확인"
echo "========================================"
echo "로그 위치: $LOG_DIR"
echo ""

# 명령어 실행
if [ "$FOLLOW" = true ]; then
    if [ "$LOG_TYPE" = "all" ]; then
        tail -f $LOG_FILE
    else
        tail -f "$LOG_FILE"
    fi
else
    if [ "$LOG_TYPE" = "all" ]; then
        tail -n $LINES $LOG_FILE
    else
        tail -n $LINES "$LOG_FILE"
    fi
fi
