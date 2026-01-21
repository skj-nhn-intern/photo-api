# Python FastAPI Backend
FROM python:3.11-slim

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리를 /app으로 설정 (app 모듈의 부모 디렉토리)
WORKDIR /app

# Python 의존성 파일 복사
COPY requirements.txt .

# 의존성 설치
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사 (환경 변수 제외)
COPY . .

# .env 파일 복사 (환경 변수 로드용)
# 주의: .env 파일에 민감한 정보가 포함되어 있으므로 프로덕션에서는 Secret 사용 권장
# deploy.sh 스크립트에서 빌드 전에 .env 파일을 photo-api/.env로 복사하므로 여기서 복사
# 파일이 없어도 빌드가 성공하도록 선택적 복사 (와일드카드 사용)
COPY .env* ./

# Entrypoint 스크립트 복사 및 실행 권한 부여
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 환경 변수 설정 (기본값)
ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL=sqlite+aiosqlite:///./photo_api.db

# 포트 노출
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Entrypoint 스크립트 실행
ENTRYPOINT ["/entrypoint.sh"]

