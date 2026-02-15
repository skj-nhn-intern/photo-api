"""
Health check endpoints for monitoring and load balancer.
Optimized for VM autoscaling environments.
"""
import asyncio
from datetime import datetime
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.config import get_settings
from app.database import get_db_context
from app.utils.prometheus_metrics import health_check_status

settings = get_settings()
router = APIRouter(tags=["Health"])

# Health check 타임아웃 (로드밸런서가 빠르게 판단할 수 있도록)
HEALTH_CHECK_TIMEOUT = 2.0  # seconds


@router.get("/health")
async def health_check():
    """
    Comprehensive health check with dependency verification.
    
    Returns 200 OK if all dependencies are healthy, 503 Service Unavailable otherwise.
    Used by load balancers and monitoring systems.
    """
    checks = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "instance": settings.instance_ip or settings.node_name or "unknown",  # 인스턴스 식별 (autoscaling 환경)
        "version": settings.app_version,
        "checks": {}
    }
    overall_healthy = True
    
    # Database check with timeout (autoscaling 환경: 빠른 응답 필요)
    try:
        async with asyncio.timeout(HEALTH_CHECK_TIMEOUT):
            async with get_db_context() as db:
                await db.execute(select(1))
        checks["checks"]["database"] = "healthy"
        health_check_status.labels(check="database").set(1)
    except asyncio.TimeoutError:
        checks["checks"]["database"] = "timeout"
        checks["checks"]["database_error"] = f"Health check timeout ({HEALTH_CHECK_TIMEOUT}s)"
        health_check_status.labels(check="database").set(0)
        overall_healthy = False
    except Exception as e:
        checks["checks"]["database"] = "unhealthy"
        checks["checks"]["database_error"] = str(e)[:100]
        health_check_status.labels(check="database").set(0)
        overall_healthy = False
    
    # Object Storage check (optional, non-blocking)
    # 옵션: 토큰 존재 여부만 확인 (빠름) 또는 실제 API 호출 (정확함)
    try:
        from app.services.nhn_object_storage import get_storage_service
        storage = get_storage_service()
        
        # 빠른 체크: 토큰 존재 여부만 확인
        if storage._token:
            checks["checks"]["object_storage"] = "healthy"
            health_check_status.labels(check="object_storage").set(1)
        else:
            checks["checks"]["object_storage"] = "unknown"
            health_check_status.labels(check="object_storage").set(0)
    except Exception as e:
        checks["checks"]["object_storage"] = "unhealthy"
        checks["checks"]["object_storage_error"] = str(e)[:100]
        health_check_status.labels(check="object_storage").set(0)
        # Object Storage는 선택적이므로 전체 상태에 영향 없음
    
    # Overall status
    if not overall_healthy:
        checks["status"] = "unhealthy"
        health_check_status.labels(check="overall").set(0)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=checks
        )
    
    health_check_status.labels(check="overall").set(1)
    return checks


@router.get("/health/liveness")
async def liveness_check():
    """
    Simple liveness check (always returns 200 if process is running).
    
    Kubernetes liveness probe용.
    프로세스가 실행 중이면 항상 200 OK 반환.
    """
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}


@router.get("/health/readiness")
async def readiness_check():
    """
    Readiness check (same as /health but for Kubernetes).
    
    Kubernetes readiness probe용.
    /health와 동일하지만 Kubernetes에서 사용하는 엔드포인트.
    """
    return await health_check()


@router.get("/health/detailed")
async def detailed_health_check():
    """
    Detailed health check with actual external service calls.
    
    실제 외부 서비스 API 호출을 수행하여 정확한 상태를 확인합니다.
    Health check보다 느리지만 더 정확합니다.
    
    주의: 이 엔드포인트는 로드밸런서 Health check에 사용하지 마세요.
    모니터링 시스템에서만 사용하세요.
    """
    checks = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "instance": settings.instance_ip or settings.node_name or "unknown",
        "version": settings.app_version,
        "checks": {}
    }
    overall_healthy = True
    
    # Database check (기존과 동일)
    try:
        async with asyncio.timeout(HEALTH_CHECK_TIMEOUT):
            async with get_db_context() as db:
                await db.execute(select(1))
        checks["checks"]["database"] = "healthy"
        health_check_status.labels(check="database").set(1)
    except asyncio.TimeoutError:
        checks["checks"]["database"] = "timeout"
        health_check_status.labels(check="database").set(0)
        overall_healthy = False
    except Exception as e:
        checks["checks"]["database"] = "unhealthy"
        checks["checks"]["database_error"] = str(e)[:100]
        health_check_status.labels(check="database").set(0)
        overall_healthy = False
    
    # Object Storage 실제 API 호출 테스트 (타임아웃 1초)
    try:
        from app.services.nhn_object_storage import get_storage_service
        storage = get_storage_service()
        
        # 실제 인증 토큰 획득 테스트 (가벼운 작업)
        async with asyncio.timeout(1.0):
            token = await storage._get_auth_token()
            if token:
                checks["checks"]["object_storage"] = "healthy"
                health_check_status.labels(check="object_storage").set(1)
            else:
                checks["checks"]["object_storage"] = "unhealthy"
                checks["checks"]["object_storage_error"] = "No auth token"
                health_check_status.labels(check="object_storage").set(0)
    except asyncio.TimeoutError:
        checks["checks"]["object_storage"] = "timeout"
        health_check_status.labels(check="object_storage").set(0)
        # Object Storage는 선택적이므로 전체 상태에 영향 없음
    except Exception as e:
        checks["checks"]["object_storage"] = "unhealthy"
        checks["checks"]["object_storage_error"] = str(e)[:100]
        health_check_status.labels(check="object_storage").set(0)
        # Object Storage는 선택적이므로 전체 상태에 영향 없음
    
    if not overall_healthy:
        checks["status"] = "unhealthy"
        health_check_status.labels(check="overall").set(0)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=checks
        )
    
    health_check_status.labels(check="overall").set(1)
    return checks
