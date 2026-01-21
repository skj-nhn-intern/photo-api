"""
Authentication router for user registration and login.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserLogin, Token
from app.services.auth import AuthService
from app.dependencies.auth import get_current_active_user
from app.services.nhn_logger import log_error

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
        return UserResponse.model_validate(user)
    except ValueError as e:
        log_error(
            "Registration failed",
            error_message=str(e),
            email=user_data.email,
            username=user_data.username,
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
    
    token = await auth_service.login(login_data.email, login_data.password)
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
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
