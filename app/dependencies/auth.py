"""
Authentication dependencies for FastAPI.
"""
import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth import AuthService
from app.utils.security import decode_access_token

logger = logging.getLogger("app.auth")

# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency to get the current authenticated user.
    
    Args:
        credentials: Bearer token from request header
        db: Database session
        
    Returns:
        Current authenticated User
        
    Raises:
        HTTPException: If token is missing, invalid, or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not credentials:
        logger.warning("Auth failed", extra={"event": "auth", "reason": "no_token"})
        raise credentials_exception

    token_payload = decode_access_token(credentials.credentials)

    if token_payload is None:
        logger.warning("Auth failed", extra={"event": "auth", "reason": "invalid_or_expired_token"})
        raise credentials_exception

    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(token_payload.sub)

    if user is None:
        logger.warning("Auth failed", extra={"event": "auth", "reason": "user_not_found", "user_id": token_payload.sub})
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency to get the current active user.
    
    Args:
        current_user: User from get_current_user dependency
        
    Returns:
        Current active User
        
    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.is_active:
        logger.warning("Inactive user rejected", extra={"event": "auth", "reason": "inactive", "user_id": current_user.id})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Dependency to optionally get the current user.
    Returns None if no valid token is provided.
    
    Args:
        credentials: Bearer token from request header
        db: Database session
        
    Returns:
        Current User or None
    """
    if not credentials:
        return None
    
    token_payload = decode_access_token(credentials.credentials)
    
    if token_payload is None:
        return None
    
    auth_service = AuthService(db)
    return await auth_service.get_user_by_id(token_payload.sub)
