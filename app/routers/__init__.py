"""
API routers package.
"""
from app.routers.auth import router as auth_router
from app.routers.photos import router as photos_router
from app.routers.albums import router as albums_router
from app.routers.share import router as share_router

__all__ = ["auth_router", "photos_router", "albums_router", "share_router"]
