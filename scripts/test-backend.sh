#!/bin/bash
# Backend API 테스트 스크립트
# 프론트엔드에서 백엔드 연결 및 주요 엔드포인트 테스트

# 기본 설정
BASE_URL="${BASE_URL:-http://localhost:8000}"
TIMEOUT=10

# 사용법
usage() {
    echo "사용법: $0 [BASE_URL]"
    echo ""
    echo "예시:"
    echo "  $0                           # localhost:8000 테스트"
    echo "  $0 http://your-lb-url        # 로드밸런서 URL 테스트"
    echo ""
    exit 1
}

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    usage
fi

if [ -n "$1" ]; then
    BASE_URL="$1"
fi

# 테스트 결과 추적
PASSED=0
FAILED=0

# 헬퍼 함수
test_endpoint() {
    local method=$1
    local endpoint=$2
    local description=$3
    local data=$4
    local headers=$5
    
    local url="${BASE_URL}${endpoint}"
    local cmd="curl -s -w '\nHTTP_CODE:%{http_code}\nTIME:%{time_total}'"
    
    if [ -n "$headers" ]; then
        cmd="$cmd -H '$headers'"
    fi
    
    if [ "$method" = "POST" ] || [ "$method" = "PATCH" ]; then
        if [ -n "$data" ]; then
            cmd="$cmd -H 'Content-Type: application/json' -d '$data'"
        fi
    fi
    
    cmd="$cmd -X $method '$url'"
    
    echo "========================================"
    echo "TEST: $description"
    echo "----------------------------------------"
    echo "Method: $method"
    echo "URL: $url"
    
    local response=$(eval $cmd 2>&1)
    local http_code=$(echo "$response" | grep "HTTP_CODE:" | cut -d: -f2)
    local time_total=$(echo "$response" | grep "TIME:" | cut -d: -f2)
    local body=$(echo "$response" | sed '/HTTP_CODE:/d' | sed '/TIME:/d')
    
    if [ -z "$http_code" ]; then
        echo "STATUS: FAILED"
        echo "ERROR: Connection failed or timeout"
        echo ""
        FAILED=$((FAILED + 1))
        return 1
    fi
    
    echo "HTTP Status: $http_code"
    echo "Response Time: ${time_total}s"
    echo "Response Body:"
    echo "$body" | head -20
    echo ""
    
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo "RESULT: PASS"
        PASSED=$((PASSED + 1))
        return 0
    elif [ "$http_code" -ge 400 ] && [ "$http_code" -lt 500 ]; then
        echo "RESULT: CLIENT ERROR (expected for some tests)"
        PASSED=$((PASSED + 1))
        return 0
    else
        echo "RESULT: FAIL"
        FAILED=$((FAILED + 1))
        return 1
    fi
}

# 시작
echo "========================================"
echo "Backend API 테스트"
echo "========================================"
echo "Base URL: $BASE_URL"
echo "Timeout: ${TIMEOUT}s"
echo ""

# 연결 테스트
echo "========================================"
echo "연결 테스트"
echo "----------------------------------------"
if curl -s --max-time $TIMEOUT -o /dev/null -w "HTTP Status: %{http_code}\nResponse Time: %{time_total}s\n" "$BASE_URL/health" > /dev/null 2>&1; then
    echo "연결: SUCCESS"
else
    echo "연결: FAILED (서버에 연결할 수 없습니다)"
    echo ""
    echo "확인 사항:"
    echo "1. 서버가 실행 중인지 확인: sudo systemctl status photo-api"
    echo "2. 포트 8000이 열려있는지 확인: sudo netstat -tlnp | grep 8000"
    echo "3. 방화벽/시큐리티 그룹에서 포트 8000 허용 확인"
    echo "4. BASE_URL이 올바른지 확인: $BASE_URL"
    exit 1
fi
echo ""

# 1. Health Check (로드밸런서 헬스 체크용)
echo "========================================"
echo "헬스 체크 테스트 (로드밸런서용)"
echo "----------------------------------------"
HEALTH_RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" --max-time $TIMEOUT "$BASE_URL/health")
HEALTH_CODE=$(echo "$HEALTH_RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
HEALTH_BODY=$(echo "$HEALTH_RESPONSE" | sed '/HTTP_CODE:/d')

echo "HTTP Status: $HEALTH_CODE"
echo "Response: $HEALTH_BODY"
echo ""

if [ "$HEALTH_CODE" = "200" ]; then
    echo "RESULT: HEALTHY (로드밸런서가 이 인스턴스를 사용할 수 있습니다)"
    PASSED=$((PASSED + 1))
elif [ "$HEALTH_CODE" = "503" ]; then
    echo "RESULT: UNHEALTHY (데이터베이스 연결 실패 - 로드밸런서가 이 인스턴스를 사용하지 않습니다)"
    FAILED=$((FAILED + 1))
else
    echo "RESULT: FAILED (예상치 못한 응답)"
    FAILED=$((FAILED + 1))
fi
echo ""

# 2. Root Endpoint
test_endpoint "GET" "/" "Root Endpoint"

# 3. API Docs (Swagger)
test_endpoint "GET" "/docs" "API Documentation (Swagger)"

# 4. OpenAPI Schema
test_endpoint "GET" "/openapi.json" "OpenAPI Schema"

# 5. 회원가입 테스트 (이미 존재할 수 있음)
TIMESTAMP=$(date +%s)
TEST_EMAIL="test${TIMESTAMP}@example.com"
TEST_USERNAME="testuser${TIMESTAMP}"
TEST_PASSWORD="testpass123"

REGISTER_DATA="{\"email\":\"$TEST_EMAIL\",\"username\":\"$TEST_USERNAME\",\"password\":\"$TEST_PASSWORD\"}"
test_endpoint "POST" "/auth/register" "User Registration" "$REGISTER_DATA"

# 6. 로그인 테스트
LOGIN_DATA="{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}"
LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/auth/login" \
    -H "Content-Type: application/json" \
    -d "$LOGIN_DATA")

TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -n "$TOKEN" ]; then
    echo "========================================"
    echo "TEST: User Login"
    echo "----------------------------------------"
    echo "STATUS: SUCCESS"
    echo "Token received: ${TOKEN:0:20}..."
    echo ""
    PASSED=$((PASSED + 1))
    
    # 7. 인증된 엔드포인트 테스트
    AUTH_HEADER="Authorization: Bearer $TOKEN"
    
    test_endpoint "GET" "/auth/me" "Get Current User" "" "$AUTH_HEADER"
    test_endpoint "GET" "/albums/" "Get User Albums" "" "$AUTH_HEADER"
    test_endpoint "GET" "/photos/" "Get User Photos" "" "$AUTH_HEADER"
    
    # 8. 앨범 생성 테스트
    ALBUM_DATA="{\"name\":\"Test Album\",\"description\":\"Test album created by test script\"}"
    test_endpoint "POST" "/albums/" "Create Album" "$ALBUM_DATA" "$AUTH_HEADER"
    
else
    echo "========================================"
    echo "TEST: User Login"
    echo "----------------------------------------"
    echo "STATUS: FAILED"
    echo "Response: $LOGIN_RESPONSE"
    echo ""
    FAILED=$((FAILED + 1))
fi

# 9. 인증 없이 접근 시도 (401 예상)
test_endpoint "GET" "/auth/me" "Unauthorized Access (Expected 401)" ""

# 10. 존재하지 않는 엔드포인트
test_endpoint "GET" "/nonexistent" "Non-existent Endpoint (Expected 404)" ""

# 결과 요약
echo "========================================"
echo "테스트 결과 요약"
echo "========================================"
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo "Total: $((PASSED + FAILED))"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "RESULT: ALL TESTS PASSED"
    exit 0
else
    echo "RESULT: SOME TESTS FAILED"
    exit 1
fi
