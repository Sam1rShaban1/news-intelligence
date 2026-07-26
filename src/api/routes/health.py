"""Health check route."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.db.models.article import Article
from src.db.models.source import Source

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict:
    """System health — DB connectivity and article counts."""
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    article_count = db.scalar(select(func.count(Article.id))) or 0
    source_count = db.scalar(select(func.count(Source.id))) or 0
    sources_enabled = db.scalar(
        select(func.count(Source.id)).where(Source.enabled.is_(True))
    ) or 0

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "articles": article_count,
        "sources": source_count,
        "sources_enabled": sources_enabled,
    }
