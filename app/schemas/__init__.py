"""
Pydantic schemas package.
All schemas are exported here for easy import.
"""
from app.schemas.user import (
    UserCreate,
    UserResponse,
    UserLogin,
    Token,
    TokenPayload,
)
from app.schemas.photo import (
    PhotoCreate,
    PhotoResponse,
    PhotoUpdate,
    PhotoWithUrl,
)
from app.schemas.album import (
    AlbumCreate,
    AlbumResponse,
    AlbumUpdate,
    AlbumWithPhotos,
    AlbumPhotoAdd,
    AlbumPhotoRemove,
)
from app.schemas.share import (
    ShareLinkCreate,
    ShareLinkResponse,
    SharedAlbumResponse,
)

__all__ = [
    # User schemas
    "UserCreate",
    "UserResponse",
    "UserLogin",
    "Token",
    "TokenPayload",
    # Photo schemas
    "PhotoCreate",
    "PhotoResponse",
    "PhotoUpdate",
    "PhotoWithUrl",
    # Album schemas
    "AlbumCreate",
    "AlbumResponse",
    "AlbumUpdate",
    "AlbumWithPhotos",
    "AlbumPhotoAdd",
    "AlbumPhotoRemove",
    # Share schemas
    "ShareLinkCreate",
    "ShareLinkResponse",
    "SharedAlbumResponse",
]
