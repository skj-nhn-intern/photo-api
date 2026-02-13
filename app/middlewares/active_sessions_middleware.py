"""
활성 세션 메트릭 미들웨어.

인증된 요청이 끝날 때 photo_api_active_sessions Gauge를 1 감소시킵니다.
(get_current_user 성공 시 증가한 값을 요청 종료 시 반영)
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.utils.prometheus_metrics import active_sessions


class ActiveSessionsMiddleware(BaseHTTPMiddleware):
    """요청 종료 시 활성 세션 메트릭 감소."""

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        finally:
            if getattr(request.state, "_active_sessions_metric_inc", False):
                active_sessions.dec()
