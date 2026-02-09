"""
Security utility functions for password hashing and JWT token management.
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings
from app.schemas.user import TokenPayload

settings = get_settings()

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password string
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.
    
    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to compare against
        
    Returns:
        True if password matches
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    user_id: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.
    
    Args:
        user_id: User ID to encode in the token
        expires_delta: Optional expiration time delta
        
    Returns:
        Encoded JWT token string
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    
    expire = datetime.utcnow() + expires_delta
    
    to_encode = {
        "sub": str(user_id),  # JWT subject must be a string
        "exp": expire,
    }
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    
    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenPayload]:
    """
    Decode and validate a JWT access token.
    
    Args:
        token: JWT token string
        
    Returns:
        TokenPayload if valid, None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        
        user_id = payload.get("sub")
        exp = payload.get("exp")
        
        if user_id is None:
            return None
        
        return TokenPayload(
            sub=int(user_id),
            exp=datetime.fromtimestamp(exp),
        )
        
    except JWTError:
        return None


def create_image_access_token(photo_id: int) -> str:
    """
    Create a short-lived JWT for image access (proxy URL).
    Only issued to authorized users; token in URL limits exposure window.
    """
    expire = datetime.utcnow() + timedelta(seconds=settings.image_token_expire_seconds)
    to_encode = {
        "sub": str(photo_id),
        "exp": expire,
        "scope": "image",
    }
    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def verify_image_access_token(token: str) -> Optional[int]:
    """
    Verify image access token and return photo_id if valid.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("scope") != "image":
            return None
        sub = payload.get("sub")
        if sub is None:
            return None
        return int(sub)
    except (JWTError, ValueError, TypeError):
        return None


def generate_share_token(length: int = 32) -> str:
    """
    Generate a secure random token for share links.
    
    Args:
        length: Length of the token (default 32 characters)
        
    Returns:
        Random URL-safe token string
    """
    return secrets.token_urlsafe(length)


def generate_unique_filename(original_filename: str) -> str:
    """
    Generate a unique filename for uploaded files.
    
    Args:
        original_filename: Original filename from upload
        
    Returns:
        Unique filename with original extension
    """
    import uuid
    from pathlib import Path
    
    ext = Path(original_filename).suffix
    unique_id = uuid.uuid4().hex
    return f"{unique_id}{ext}"
