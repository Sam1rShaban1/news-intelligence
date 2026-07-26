"""API routes package."""

from .health import router as health_router
from .articles import router as articles_router
from .search import router as search_router

__all__ = ["health_router", "articles_router", "search_router"]
