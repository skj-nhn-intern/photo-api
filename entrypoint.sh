#!/bin/sh
set -e

# PYTHONPATH에 /app 추가
export PYTHONPATH=/app:$PYTHONPATH

# /app으로 이동
cd /app

# uvicorn 실행
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

