#!/bin/bash
# 프라이빗 오브젝트 스토리지(code-repository 컨테이너의 api/ 폴더)에서
# 1~4번 설정 스크립트와 photo-api.zip을 다운로드한 뒤, 압축 해제 후 스크립트를 순서대로 실행합니다.
#
# 오브젝트 스토리지 api/ 폴더 구조 가정:
#   api/1-install-python.sh
#   api/2-setup-photo-api.sh
#   api/3-setup-promtail.sh
#   api/4-setup-telegraf.sh
#   api/photo-api.zip  (압축 해제 시 photo-api/ 또는 app·scripts 등 프로젝트 루트)
#
# 사용법:
#   export NHN_STORAGE_IAM_USER="your-iam-user"
#   export NHN_STORAGE_IAM_PASSWORD="your-password"
#   export NHN_STORAGE_TENANT_ID="your-tenant-id"
#   export NHN_STORAGE_AUTH_URL="https://api-identity-infrastructure.nhncloudservice.com/v2.0"
#   export NHN_STORAGE_BASE_URL="https://kr1-api-object-storage.nhncloudservice.com/v1"
#   ./download-and-run-setup.sh
#
# 또는 프로젝트 루트에 .env 가 있으면 로드 후 실행 (민감 정보는 .env에 두고 git에 넣지 마세요):
#   ./download-and-run-setup.sh
#
# 옵션:
#   DOWNLOAD_DIR=./my-dir ./download-and-run-setup.sh  # 다운로드 경로 (기본: 현재 디렉터리)
#   CONTAINER=code-repository ./download-and-run-setup.sh  # 컨테이너 이름 (기본: code-repository)
#   SKIP_RUN=1 ./download-and-run-setup.sh  # 다운로드만, 스크립트 실행 생략

set -e

CONTAINER="${CONTAINER:-code-repository}"
API_PREFIX="api"
DOWNLOAD_DIR="${DOWNLOAD_DIR:-.}"
SKIP_RUN="${SKIP_RUN:-0}"

FILES=(
    "1-install-python.sh"
    "2-setup-photo-api.sh"
    "3-setup-promtail.sh"
    "4-setup-telegraf.sh"
    "photo-api.zip"
)

# .env 로드 (KEY=VALUE 형식, # 주석과 빈 줄 제외)
load_env() {
    if [ -f ".env" ]; then
        set -a
        while IFS= read -r line; do
            [[ "$line" =~ ^#.*$ ]] && continue
            [[ -z "${line// }" ]] && continue
            # export KEY=VALUE (값에 = 포함 시 첫 번째 = 만 구분)
            if [[ "$line" == *=* ]]; then
                export "$line"
            fi
        done < .env
        set +a
        echo "Loaded .env"
    fi
}

# NHN IAM 토큰 발급 (Keystone v2)
# 출력: TOKEN과 TENANT_ID (한 줄씩)
get_token() {
    local auth_url="${NHN_STORAGE_AUTH_URL%/}"
    if [[ "$auth_url" == */v2.0 ]]; then
        auth_url="${auth_url}/tokens"
    else
        auth_url="${auth_url}/tokens"
    fi

    local user="${NHN_STORAGE_IAM_USER}"
    local pass="${NHN_STORAGE_IAM_PASSWORD}"
    local tenant_id="${NHN_STORAGE_TENANT_ID}"

    if [ -z "$user" ] || [ -z "$pass" ] || [ -z "$tenant_id" ]; then
        echo "Error: NHN_STORAGE_IAM_USER, NHN_STORAGE_IAM_PASSWORD, NHN_STORAGE_TENANT_ID 를 설정하세요." >&2
        exit 1
    fi

    local resp
    resp=$(curl -s -S -X POST "$auth_url" \
        -H "Content-Type: application/json" \
        -d "{\"auth\":{\"tenantId\":\"$tenant_id\",\"passwordCredentials\":{\"username\":\"$user\",\"password\":\"$pass\"}}}") || true

    if [ -z "$resp" ]; then
        echo "Error: IAM 인증 요청 실패 (연결 확인)" >&2
        exit 1
    fi

    local token
    token=$(echo "$resp" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    if [ -z "$token" ]; then
        token=$(echo "$resp" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('access', {}).get('token', {}).get('id', '') or d.get('token', {}).get('id', ''))
except Exception:
    print('')
" 2>/dev/null)
    fi

    local got_tenant
    got_tenant=$(echo "$resp" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    t = d.get('access', {}).get('token', {}).get('tenant', {})
    print(t.get('id', '') if isinstance(t, dict) else '')
except Exception:
    print('')
" 2>/dev/null)

    if [ -z "$token" ]; then
        echo "Error: IAM 토큰을 받지 못했습니다. 응답: $resp" >&2
        exit 1
    fi

    [ -n "$got_tenant" ] && tenant_id="$got_tenant"
    echo "$token"
    echo "$tenant_id"
}

# 오브젝트 스토리지에서 파일 다운로드
# 인자: 토큰, 스토리지 베이스 URL(계정 포함), 오브젝트 경로, 저장 경로
download_one() {
    local token="$1"
    local base_url="$2"
    local object_path="$3"
    local save_path="$4"
    local url="${base_url}/${object_path}"
    echo "Downloading: $object_path -> $save_path"
    if ! curl -s -S -f -o "$save_path" -H "X-Auth-Token: $token" "$url"; then
        echo "Error: 다운로드 실패: $object_path" >&2
        return 1
    fi
    return 0
}

main() {
    load_env

    NHN_STORAGE_BASE_URL="${NHN_STORAGE_BASE_URL:-$NHN_STORAGE_URL}"
    if [ -z "$NHN_STORAGE_BASE_URL" ]; then
        echo "Error: NHN_STORAGE_BASE_URL 또는 NHN_STORAGE_URL 을 설정하세요. (예: https://kr1-api-object-storage.nhncloudservice.com/v1)" >&2
        exit 1
    fi
    NHN_STORAGE_BASE_URL="${NHN_STORAGE_BASE_URL%/}"

    # IAM 토큰 발급 (항상 필요)
    AUTH_OUTPUT=$(get_token)
    TOKEN=$(echo "$AUTH_OUTPUT" | sed -n '1p')
    TENANT_ID=$(echo "$AUTH_OUTPUT" | sed -n '2p')
    [ -z "$TENANT_ID" ] && TENANT_ID="$NHN_STORAGE_TENANT_ID"

    # 스토리지 베이스 URL: .../v1/AUTH_tenant_id (컨테이너 제외)
    if [[ "$NHN_STORAGE_BASE_URL" == *"/AUTH_"* ]]; then
        # 예: .../v1/AUTH_xxx/photo -> .../v1/AUTH_xxx
        STORAGE_BASE="${NHN_STORAGE_BASE_URL%/*}"
    else
        STORAGE_BASE="${NHN_STORAGE_BASE_URL}/AUTH_${TENANT_ID}"
    fi

    mkdir -p "$DOWNLOAD_DIR"
    cd "$DOWNLOAD_DIR"
    DOWNLOAD_DIR_ABS="$(pwd)"
    cd - >/dev/null

    for f in "${FILES[@]}"; do
        object_path="${CONTAINER}/${API_PREFIX}/${f}"
        save_path="${DOWNLOAD_DIR_ABS}/${f}"
        download_one "$TOKEN" "$STORAGE_BASE" "$object_path" "$save_path" || exit 1
    done

    echo ""
    echo "========================================"
    echo "다운로드 완료: $DOWNLOAD_DIR_ABS"
    echo "========================================"

    if [ "$SKIP_RUN" = "1" ]; then
        echo "SKIP_RUN=1 이므로 스크립트 실행을 건너뜁니다."
        exit 0
    fi

    cd "$DOWNLOAD_DIR_ABS"
    # photo-api.zip 압축 해제 (2-setup-photo-api.sh는 scripts/ 의 부모가 레포 루트인 구조를 기대함)
    if [ -f "photo-api.zip" ]; then
        echo "photo-api.zip 압축 해제 중..."
        unzip -o -q photo-api.zip
        if [ -d "photo-api" ]; then
            REPO_ROOT="${DOWNLOAD_DIR_ABS}/photo-api"
        else
            REPO_ROOT="$DOWNLOAD_DIR_ABS"
        fi
    else
        REPO_ROOT="$DOWNLOAD_DIR_ABS"
    fi
    SCRIPTS_DIR="${REPO_ROOT}/scripts"
    mkdir -p "$SCRIPTS_DIR"
    for sh_name in 1-install-python.sh 2-setup-photo-api.sh 3-setup-promtail.sh 4-setup-telegraf.sh; do
        [ -f "${DOWNLOAD_DIR_ABS}/${sh_name}" ] && cp -f "${DOWNLOAD_DIR_ABS}/${sh_name}" "$SCRIPTS_DIR/"
    done
    cd "$SCRIPTS_DIR"

    for i in 1 2 3 4; do
        sh_name="${i}-install-python.sh"
        [ "$i" -eq 2 ] && sh_name="2-setup-photo-api.sh"
        [ "$i" -eq 3 ] && sh_name="3-setup-promtail.sh"
        [ "$i" -eq 4 ] && sh_name="4-setup-telegraf.sh"
        path="${SCRIPTS_DIR}/${sh_name}"
        if [ ! -f "$path" ]; then
            echo "Warning: $path 없음, 건너뜀" >&2
            continue
        fi
        chmod +x "$path"
        echo ""
        echo "========================================"
        echo "실행: $path"
        echo "========================================"
        sudo "$path" || { echo "실패: $path"; exit 1; }
    done

    echo ""
    echo "========================================"
    echo "모든 설정 스크립트 실행 완료"
    echo "========================================"
}

main "$@"
