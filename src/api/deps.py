"""FastAPI dependencies — shared request-scoped resources."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from src.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Yield a database session per request, closing it when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
