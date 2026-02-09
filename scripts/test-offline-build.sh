#!/usr/bin/env bash
# 로컬에서 오프라인 빌드를 테스트하는 스크립트
# GitHub Actions 워크플로우를 시뮬레이션합니다.
#
# 사용법:
#   ./scripts/test-offline-build.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORK_DIR="$PROJECT_ROOT/test-build"

PROMTAIL_VERSION="${PROMTAIL_VERSION:-3.6.4}"

echo "================================================"
echo "오프라인 빌드 테스트"
echo "================================================"
echo "작업 디렉토리: $WORK_DIR"
echo ""

# 작업 디렉토리 준비
echo "📁 작업 디렉토리 준비 중..."
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"/{offline-packages,simulated-instance}

cd "$PROJECT_ROOT"

# 1단계: 오프라인 패키지 다운로드 (GitHub Actions runner가 하는 작업)
echo ""
echo "================================================"
echo "1단계: 오프라인 패키지 다운로드"
echo "================================================"

# Python 패키지 다운로드
echo "📦 Python 패키지 다운로드 중..."
pip download -r requirements.txt -d "$WORK_DIR/offline-packages/" --no-cache-dir
echo "✅ Python 패키지 다운로드 완료: $(ls -1 $WORK_DIR/offline-packages/*.whl | wc -l)개 패키지"

# Promtail 바이너리 다운로드
echo ""
echo "📥 Promtail 바이너리 다운로드 중..."
if [[ -f "$WORK_DIR/offline-packages/promtail.zip" ]]; then
  echo "  이미 존재함, 건너뜀"
else
  curl -sSL --progress-bar -o "$WORK_DIR/offline-packages/promtail.zip" \
    "https://github.com/grafana/loki/releases/download/v${PROMTAIL_VERSION}/promtail-linux-amd64.zip"
  echo "✅ Promtail 다운로드 완료 ($(du -h $WORK_DIR/offline-packages/promtail.zip | cut -f1))"
fi

# 2단계: 시뮬레이션된 인스턴스에 복사
echo ""
echo "================================================"
echo "2단계: 소스 코드 및 패키지 복사"
echo "================================================"

# 소스 코드 복사
echo "📤 소스 코드 복사 중..."
rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='venv' --exclude='.env' --exclude='*.log' --exclude='test-build' \
  "$PROJECT_ROOT/" "$WORK_DIR/simulated-instance/"
echo "✅ 소스 코드 복사 완료"

# 오프라인 패키지 복사
echo "📦 오프라인 패키지 복사 중..."
rsync -a "$WORK_DIR/offline-packages/" "$WORK_DIR/simulated-instance/offline-packages/"
echo "✅ 오프라인 패키지 복사 완료"

# 3단계: 오프라인 설치 테스트 (가상환경 사용)
echo ""
echo "================================================"
echo "3단계: 오프라인 설치 테스트"
echo "================================================"

cd "$WORK_DIR/simulated-instance"

# Python 가상환경 생성
echo "🐍 Python 가상환경 생성 중..."
python3 -m venv test-venv
echo "✅ 가상환경 생성 완료"

# pip 업그레이드 (오프라인)
echo ""
echo "📦 pip 업그레이드 중 (오프라인)..."
test-venv/bin/pip install --upgrade pip --no-index --find-links=offline-packages/ -q || {
  echo "⚠️  pip 업그레이드 실패 (무시하고 계속)"
}

# 의존성 설치 (오프라인)
echo ""
echo "📦 의존성 설치 중 (오프라인)..."
test-venv/bin/pip install --no-index --find-links=offline-packages/ -r requirements.txt
echo "✅ 의존성 설치 완료"

# Promtail 압축 해제
echo ""
echo "📦 Promtail 바이너리 압축 해제..."
mkdir -p promtail-test
unzip -q offline-packages/promtail.zip -d promtail-test/
PROMTAIL_BIN=$(find promtail-test -type f -name 'promtail*' ! -name '*.zip' | head -1)
if [[ -f "$PROMTAIL_BIN" ]]; then
  chmod +x "$PROMTAIL_BIN"
  echo "✅ Promtail 바이너리 준비 완료: $PROMTAIL_BIN"
  "$PROMTAIL_BIN" --version || echo "⚠️  Promtail 버전 확인 실패"
else
  echo "❌ Promtail 바이너리를 찾을 수 없습니다"
fi

# 4단계: 설치 검증
echo ""
echo "================================================"
echo "4단계: 설치 검증"
echo "================================================"

echo "🔍 설치된 패키지 확인 중..."
echo ""
echo "주요 패키지:"
test-venv/bin/pip list | grep -E '(fastapi|uvicorn|sqlalchemy|boto3|prometheus-client)' || true

echo ""
echo "📊 통계:"
echo "  - 전체 패키지 수: $(test-venv/bin/pip list | tail -n +3 | wc -l)"
echo "  - 오프라인 패키지 수: $(ls -1 offline-packages/*.whl 2>/dev/null | wc -l)"
echo "  - Promtail 바이너리: $(ls -lh "$PROMTAIL_BIN" 2>/dev/null | awk '{print $5}' || echo '없음')"

# 5단계: 간단한 import 테스트
echo ""
echo "================================================"
echo "5단계: Import 테스트"
echo "================================================"

echo "🧪 Python 모듈 import 테스트..."
test-venv/bin/python << 'PYTEST'
import sys

modules_to_test = [
    'fastapi',
    'uvicorn',
    'sqlalchemy',
    'pydantic',
    'boto3',
    'prometheus_client',
    'httpx',
    'jose',
    'passlib',
]

failed = []
for module in modules_to_test:
    try:
        __import__(module)
        print(f"  ✅ {module}")
    except ImportError as e:
        print(f"  ❌ {module}: {e}")
        failed.append(module)

if failed:
    print(f"\n❌ {len(failed)}개 모듈 import 실패: {', '.join(failed)}")
    sys.exit(1)
else:
    print("\n✅ 모든 모듈 import 성공")
PYTEST

# 최종 요약
echo ""
echo "================================================"
echo "✅ 오프라인 빌드 테스트 완료"
echo "================================================"
echo ""
echo "다음 단계:"
echo "  1. 테스트 결과 확인: $WORK_DIR"
echo "  2. 문제가 없으면 GitHub Actions 워크플로우 실행 가능"
echo "  3. 정리: rm -rf $WORK_DIR"
echo ""
echo "GitHub Actions 워크플로우 실행:"
echo "  gh workflow run build-and-test-image.yml"
echo ""
