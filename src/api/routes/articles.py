"""Article routes — list and retrieve articles."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.db.models.article import Article
from src.db.models.source import Source

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("")
def list_articles(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    source_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    since: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Paginated article list with optional filters."""
    query = select(Article)
    count_query = select(func.count(Article.id))

    if source_id is not None:
        query = query.where(Article.source_id == source_id)
        count_query = count_query.where(Article.source_id == source_id)
    if status is not None:
        query = query.where(Article.status == status)
        count_query = count_query.where(Article.status == status)
    if since is not None:
        query = query.where(Article.discovered_at >= since)
        count_query = count_query.where(Article.discovered_at >= since)

    total = db.scalar(count_query) or 0
    articles = db.execute(
        query.order_by(desc(Article.discovered_at)).limit(limit).offset(offset)
    ).scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "articles": [_article_summary(a) for a in articles],
    }


@router.get("/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)) -> dict:
    """Full article details."""
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    source = db.get(Source, article.source_id)

    return {
        "id": article.id,
        "url": article.url,
        "title": article.title,
        "author": article.author,
        "published_date": article.published_date.isoformat() if article.published_date else None,
        "content": article.content,
        "summary": article.summary,
        "language": article.language,
        "word_count": article.word_count,
        "status": article.status,
        "source": {"id": source.id, "name": source.name} if source else None,
        "discovered_at": article.discovered_at.isoformat() if article.discovered_at else None,
        "extracted_at": article.extracted_at.isoformat() if article.extracted_at else None,
    }


def _article_summary(article: Article) -> dict:
    return {
        "id": article.id,
        "title": article.title,
        "url": article.url,
        "source_id": article.source_id,
        "status": article.status,
        "word_count": article.word_count,
        "published_date": article.published_date.isoformat() if article.published_date else None,
        "discovered_at": article.discovered_at.isoformat() if article.discovered_at else None,
    }
