"""Sentiment route — sentiment analysis stats and distribution."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.db.models.article import Article

router = APIRouter(tags=["sentiment"])


@router.get("/sentiment/distribution")
def sentiment_distribution(db: Session = Depends(get_db)) -> dict:
    """Sentiment label distribution across analyzed articles."""
    rows = db.execute(
        select(
            Article.sentiment_label,
            func.count(Article.id).label("count"),
            func.avg(Article.sentiment_score).label("avg_score"),
        )
        .where(Article.sentiment_label.isnot(None))
        .group_by(Article.sentiment_label)
        .order_by(desc("count"))
    ).all()

    lang_rows = db.execute(
        select(
            Article.language,
            Article.sentiment_label,
            func.count(Article.id).label("count"),
        )
        .where(Article.sentiment_label.isnot(None))
        .group_by(Article.language, Article.sentiment_label)
    ).all()
    by_language: dict[str, dict[str, int]] = {}
    for lr in lang_rows:
        key = lr.language or "und"
        by_language.setdefault(key, {})[lr.sentiment_label] = lr.count

    return {
        "distribution": [
            {
                "label": r.sentiment_label,
                "count": r.count,
                "avg_score": round(float(r.avg_score), 4) if r.avg_score else 0,
            }
            for r in rows
        ],
        "by_language": by_language,
        "total_analyzed": sum(r.count for r in rows),
    }


@router.get("/sentiment/recent")
def recent_sentiment(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """Recent articles with their sentiment scores."""
    rows = db.execute(
        select(
            Article.id,
            Article.title,
            Article.url,
            Article.sentiment_score,
            Article.sentiment_label,
            Article.language,
            Article.analyzed_at,
        )
        .where(Article.sentiment_label.isnot(None))
        .order_by(desc(Article.analyzed_at))
        .limit(limit)
    ).all()

    return {
        "articles": [
            {
                "id": r.id,
                "title": r.title,
                "url": r.url,
                "score": r.sentiment_score,
                "label": r.sentiment_label,
                "language": r.language,
                "analyzed_at": r.analyzed_at.isoformat() if r.analyzed_at else None,
            }
            for r in rows
        ],
    }
