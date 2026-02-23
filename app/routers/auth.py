"""
Authentication router for user registration and login.
"""
import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.prometheus_metrics import (
    login_duration_seconds,
    users_total,
    user_registration_total,
    user_login_total,
)
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserLogin, Token
from app.services.auth import AuthService
from app.dependencies.auth import get_current_active_user
from app.utils.logger import log_info, log_warning, log_error

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Register a new user account.
    
    - **email**: Valid email address (must be unique)
    - **username**: Username (3-100 characters, must be unique)
    - **password**: Password (8-100 characters)
    """
    auth_service = AuthService(db)
    
    try:
        user = await auth_service.register(user_data)
        
        # 주요 비즈니스 이벤트 로깅 (INFO 레벨)
        log_info(
            "User registration completed",
            event="user_registration",
            user_id=user.id,
        )
        
        # 비즈니스 메트릭 실시간 업데이트: 회원수, 가입 시도
        users_total.labels(status="total").inc()
        users_total.labels(status="active").inc()
        user_registration_total.labels(result="success").inc()

        return UserResponse.model_validate(user)
    except ValueError as e:
        user_registration_total.labels(result="failure").inc()
        # 잠재적 문제 로깅 (WARN 레벨)
        log_warning(
            "User registration failed - validation error",
            event="user_registration",
            error_message=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed",
        )


@router.post(
    "/login",
    response_model=Token,
    summary="Login to get access token",
)
async def login(
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Login with email and password to get JWT access token.
    
    - **email**: Registered email address
    - **password**: User password
    
    Returns a JWT token that should be included in the Authorization header
    as `Bearer <token>` for authenticated endpoints.
    """
    auth_service = AuthService(db)
    start = time.perf_counter()
    token = await auth_service.login(login_data.email, login_data.password)
    duration = time.perf_counter() - start
    result = "success" if token else "failure"
    login_duration_seconds.labels(result=result).observe(duration)
    user_login_total.labels(result=result).inc()

    if not token:
        # 잠재적 문제 로깅 (WARN 레벨) - 무차별 대입 공격 탐지 가능
        log_warning(
            "Login failed - invalid credentials",
            event="user_login",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 주요 비즈니스 이벤트 로깅 (INFO 레벨)
    log_info(
        "User login successful",
        event="user_login",
    )

    return token


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    """
    Get the current authenticated user's profile.
    
    Requires authentication via Bearer token.
    """
    return UserResponse.model_validate(current_user)
