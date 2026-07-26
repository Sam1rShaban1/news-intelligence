"""Search route — PostgreSQL full-text search across articles."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select, text
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.db.models.article import Article

router = APIRouter(tags=["search"])


@router.get("/search")
def search_articles(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """
    Full-text search across article titles and content.
    Uses PostgreSQL tsvector/tsquery for efficient matching.
    """
    # Build the tsquery from user input
    # Each word becomes a prefix match: "AI policy" → "AI:* & policy:*"
    terms = q.strip().split()
    tsquery_str = " & ".join(f"{t}:*" for t in terms if t)

    if not tsquery_str:
        return {"total": 0, "results": [], "query": q}

    tsquery = func.plainto_tsquery("simple", q)
    ts_rank = func.ts_rank_cd(Article.search_vector, tsquery)

    query = (
        select(
            Article.id,
            Article.title,
            Article.url,
            Article.source_id,
            Article.published_date,
            Article.summary,
            ts_rank.label("rank"),
        )
        .where(Article.search_vector.op("@@")(tsquery))
        .order_by(desc("rank"))
        .limit(limit)
        .offset(offset)
    )

    count_query = select(func.count(Article.id)).where(
        Article.search_vector.op("@@")(tsquery)
    )

    total = db.scalar(count_query) or 0
    rows = db.execute(query).all()

    return {
        "total": total,
        "query": q,
        "results": [
            {
                "id": row.id,
                "title": row.title,
                "url": row.url,
                "source_id": row.source_id,
                "published_date": row.published_date.isoformat() if row.published_date else None,
                "summary": row.summary,
                "rank": round(row.rank, 4),
            }
            for row in rows
        ],
    }
