"""FastAPI dependencies — shared request-scoped resources."""

from collections.abc import Generator

from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session

from config.settings import settings
from src.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Yield a database session per request, closing it when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Gate every API route on a shared key when `NEWS_API_KEY` is configured.

    Auth is opt-in: if no key is configured the dependency is a no-op, preserving
    single-tenant behaviour behind a trusted reverse proxy.
    """
    if not settings.api_key:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
