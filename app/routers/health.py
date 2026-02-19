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
    "/",
    summary="Health check (fast)",
)
async def health_check() -> Dict[str, Any]:
    """
    빠른 Health Check (로드밸런서용).
    
    - 애플리케이션 실행 상태만 확인
    - 타임아웃: 2초 이내
    - DB 연결은 간단히 확인 (타임아웃 짧게)
    """
    start_time = time.perf_counter()
    
    try:
        # Ready 상태 확인
        if ready._value.get() == 0:
            health_check_status.labels(check_type="fast").set(0)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Application is shutting down",
            )
        
        # DB 연결 간단 확인 (타임아웃 1초)
        try:
            async def _check_db():
                async with engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
            
            await asyncio.wait_for(_check_db(), timeout=1.0)
        except asyncio.TimeoutError:
            logger.warning(
                "DB health check timeout",
                extra={"event": "health"},
            )
            health_check_status.labels(check_type="fast").set(0)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection timeout",
            )
        except Exception as e:
            logger.warning(
                "DB health check failed",
                extra={"event": "health", "error": str(e)},
            )
            health_check_status.labels(check_type="fast").set(0)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection failed",
            )
        
        duration = time.perf_counter() - start_time
        
        health_check_status.labels(check_type="fast").set(1)
        
        return {
            "status": "healthy",
            "duration_ms": round(duration * 1000, 2),
            "instance": settings.instance_ip or "unknown",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Health check error",
            extra={"event": "health", "error": str(e)},
            exc_info=True,
        )
        health_check_status.labels(check_type="fast").set(0)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Health check failed",
        )


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
    - Object Storage 연결 확인 (실제 API 호출)
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
    
    # Object Storage 연결 확인 (타임아웃 1초)
    if settings.nhn_storage_iam_user or settings.nhn_storage_username:
        try:
            storage_service = get_storage_service()
            # 토큰 존재 여부만 확인 (실제 API 호출은 짧게)
            token = await asyncio.wait_for(
                storage_service._get_auth_token(),
                timeout=1.0
            )
            if token:
                checks["checks"]["object_storage"] = {"status": "up"}
            else:
                checks["status"] = "unhealthy"
                checks["checks"]["object_storage"] = {
                    "status": "down",
                    "error": "Failed to get auth token",
                }
        except asyncio.TimeoutError:
            checks["status"] = "unhealthy"
            checks["checks"]["object_storage"] = {
                "status": "down",
                "error": "Timeout",
            }
        except Exception as e:
            checks["status"] = "unhealthy"
            checks["checks"]["object_storage"] = {
                "status": "down",
                "error": str(e)[:200],
            }
            logger.warning(
                "Object Storage health check failed",
                extra={"event": "health", "error": str(e)},
            )
    else:
        checks["checks"]["object_storage"] = {"status": "skipped", "reason": "Not configured"}
    
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
