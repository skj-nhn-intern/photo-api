"""
Health Check 라우터.

애플리케이션의 상태를 확인하는 엔드포인트를 제공합니다.
"""
import asyncio
import logging
import time
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.config import get_settings
from app.database import engine
from app.utils.prometheus_metrics import (
    REGISTRY,
    Gauge,
    ready,
)
from app.services.nhn_object_storage import get_storage_service

logger = logging.getLogger("app.health")
router = APIRouter(prefix="/health", tags=["Health"])

settings = get_settings()

# Health check 상태 메트릭
health_check_status = Gauge(
    "photo_api_health_check_status",
    "Health check status (1=healthy, 0=unhealthy)",
    ["check_type"],
    registry=REGISTRY,
)


@router.get(
    "",
    summary="Health check",
)
async def health_check() -> Dict[str, str]:
    """
    단순 Health Check (로드밸런서/프로브용).
    준비 상태(ready)만 보고, 200 또는 503을 반환합니다.
    """
    if ready._value.get() == 0:
        health_check_status.labels(check_type="fast").set(0)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application is shutting down",
        )
    health_check_status.labels(check_type="fast").set(1)
    return {"status": "ok"}


@router.get(
    "/liveness",
    summary="Liveness probe (Kubernetes)",
)
async def liveness_probe() -> Dict[str, str]:
    """
    Liveness Probe (Kubernetes용).
    
    애플리케이션이 살아있는지만 확인합니다.
    """
    if ready._value.get() == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application is shutting down",
        )
    
    return {"status": "alive"}


@router.get(
    "/readiness",
    summary="Readiness probe (Kubernetes)",
)
async def readiness_probe() -> Dict[str, str]:
    """
    Readiness Probe (Kubernetes용).
    
    애플리케이션이 요청을 처리할 준비가 되었는지 확인합니다.
    """
    if ready._value.get() == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application is not ready",
        )
    
    # DB 연결 확인
    try:
        async def _check_db():
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
        
        await asyncio.wait_for(_check_db(), timeout=1.0)
    except asyncio.TimeoutError:
        logger.warning(
            "Readiness check failed: DB timeout",
            extra={"event": "health"},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection timeout",
        )
    except Exception as e:
        logger.warning(
            "Readiness check failed: DB",
            extra={"event": "health", "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not ready",
        )
    
    return {"status": "ready"}


@router.get(
    "/detailed",
    summary="Detailed health check (monitoring)",
)
async def detailed_health_check() -> Dict[str, Any]:
    """
    상세 Health Check (모니터링 시스템용).
    
    - DB 연결 확인
    - OBS API server: **이 API 서버 → OBS 인증 엔드포인트** 연결 가능 여부만 확인.
      (OBS 서비스 전체 상태가 아닌, 우리 인스턴스의 연동/의존성 상태임.)
    - CDN API server: 별도 체크 없음. 실제 요청 시 메트릭(service=cdn_api_server)으로만 파악 가능.
    - 타임아웃: 5초 이내
    """
    start_time = time.perf_counter()
    checks: Dict[str, Any] = {
        "status": "healthy",
        "checks": {},
    }
    
    # Ready 상태 확인
    if ready._value.get() == 0:
        checks["status"] = "unhealthy"
        checks["checks"]["ready"] = {"status": "down", "error": "Application is shutting down"}
        health_check_status.labels(check_type="detailed").set(0)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=checks,
        )
    
    # DB 연결 확인
    try:
        async def _check_db():
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
        
        await asyncio.wait_for(_check_db(), timeout=1.0)
        checks["checks"]["database"] = {"status": "up"}
    except asyncio.TimeoutError:
        checks["status"] = "unhealthy"
        checks["checks"]["database"] = {
            "status": "down",
            "error": "Timeout",
        }
    except Exception as e:
        checks["status"] = "unhealthy"
        checks["checks"]["database"] = {
            "status": "down",
            "error": str(e)[:200],
        }
        logger.warning(
            "DB health check failed",
            extra={"event": "health", "error": str(e)},
        )
    
    # OBS API server: 이 API 서버 → OBS 인증 엔드포인트 연결 가능 여부만 확인.
    # (OBS 서비스 전체 가동 상태가 아님. 연동/의존성 관점의 체크.)
    if settings.nhn_storage_iam_user or settings.nhn_storage_username:
        try:
            storage_service = get_storage_service()
            token = await asyncio.wait_for(
                storage_service._get_auth_token(),
                timeout=1.0
            )
            if token:
                checks["checks"]["obs_api_server"] = {
                    "status": "up",
                    "scope": "API server → OBS auth endpoint connectivity only",
                }
            else:
                checks["status"] = "unhealthy"
                checks["checks"]["obs_api_server"] = {
                    "status": "down",
                    "error": "Failed to get auth token",
                    "scope": "API server → OBS auth endpoint connectivity only",
                }
        except asyncio.TimeoutError:
            checks["status"] = "unhealthy"
            checks["checks"]["obs_api_server"] = {
                "status": "down",
                "error": "Timeout",
                "scope": "API server → OBS auth endpoint connectivity only",
            }
        except Exception as e:
            checks["status"] = "unhealthy"
            checks["checks"]["obs_api_server"] = {
                "status": "down",
                "error": str(e)[:200],
                "scope": "API server → OBS auth endpoint connectivity only",
            }
            logger.warning(
                "OBS API server health check failed",
                extra={"event": "health", "error": str(e)},
            )
    else:
        checks["checks"]["obs_api_server"] = {"status": "skipped", "reason": "Not configured"}
    
    duration = time.perf_counter() - start_time
    checks["duration_ms"] = round(duration * 1000, 2)
    checks["instance"] = settings.instance_ip or "unknown"
    
    # 전체 상태 확인
    if checks["status"] == "unhealthy":
        health_check_status.labels(check_type="detailed").set(0)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=checks,
        )
    
    health_check_status.labels(check_type="detailed").set(1)
    return checks
