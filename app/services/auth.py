"""
Authentication service for user management.
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, Token
from app.utils.security import hash_password, verify_password, create_access_token

logger = logging.getLogger("app.auth")


class AuthService:
    """
    Service for handling user authentication.
    Provides methods for registration, login, and user management.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def register(self, user_data: UserCreate) -> User:
        """
        Register a new user.
        
        Args:
            user_data: User registration data
            
        Returns:
            Created User model
            
        Raises:
            ValueError: If email or username already exists
        """
        # Check if email exists
        existing_email = await self._get_user_by_email(user_data.email)
        if existing_email:
            raise ValueError("Email already registered")
        existing_username = await self._get_user_by_username(user_data.username)
        if existing_username:
            raise ValueError("Username already taken")
        
        # Create new user
        hashed_password = hash_password(user_data.password)
        user = User(
            email=user_data.email,
            username=user_data.username,
            hashed_password=hashed_password,
        )
        
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        logger.info("User registered", extra={"event": "auth", "user_id": user.id})
        return user
    
    async def authenticate(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate a user with email and password.
        
        Args:
            email: User email
            password: Plain text password
            
        Returns:
            User if authentication successful, None otherwise
        """
        user = await self._get_user_by_email(email)
        
        if not user:
            # 존재하지 않는 계정 로그인 시도 (보안: email 로깅 안 함)
            logger.warning("Login failed", extra={"event": "auth", "reason": "not_found"})
            return None
        if not user.is_active:
            logger.warning("Login failed", extra={"event": "auth", "reason": "inactive", "user_id": user.id})
            return None
        if not verify_password(password, user.hashed_password):
            # 비밀번호 오류 (보안: 너무 자세한 정보 노출 방지)
            logger.warning("Login failed", extra={"event": "auth", "reason": "invalid_password", "user_id": user.id})
            return None
        logger.info("Login", extra={"event": "auth", "user_id": user.id})
        return user
    
    async def login(self, email: str, password: str) -> Optional[Token]:
        """
        Login user and return JWT token.
        
        Args:
            email: User email
            password: Plain text password
            
        Returns:
            Token if login successful, None otherwise
        """
        user = await self.authenticate(email, password)
        
        if not user:
            return None
        
        access_token = create_access_token(user.id)
        return Token(access_token=access_token)
    
    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Get user by ID.
        
        Args:
            user_id: User ID
            
        Returns:
            User if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def _get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    async def _get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()
