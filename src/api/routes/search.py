"""Search route — PostgreSQL full-text search across articles with filters."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.api.search_query import apply_filters
from src.db.models.article import Article
from src.db.models.entity import Entity
from src.db.models.entity_node import EntityNode
from src.db.models.source import Source

router = APIRouter(tags=["search"])


@router.get("/search")
def search_articles(
    q: str | None = Query(default=None, min_length=2, description="Full-text query"),
    language: str | None = Query(default=None, description="Comma-separated languages (mk,sq,en,tr)"),
    sentiment: str | None = Query(default=None, description="Comma-separated pos/neg/neutral"),
    source_id: int | None = Query(default=None, description="Filter by source id"),
    entity: str | None = Query(default=None, description="Only articles mentioning this entity (canonical text)"),
    predicate: str | None = Query(default=None, description="Only articles with a relationship of this predicate"),
    date_from: date | None = Query(default=None, description="Articles discovered on/after this date"),
    date_to: date | None = Query(default=None, description="Articles discovered on/before this date"),
    sort: str = Query(default="auto", description="rank | recent | auto"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """
    Full-text search + filtered browse across articles.
    If `q` is omitted the endpoint acts as a filtered browser. Results include
    sentiment, language, source and the article's top entities.
    """
    sort_mode = sort
    if sort_mode == "auto":
        sort_mode = "rank" if q else "recent"

    # Total count (same filters, no columns/order/limit)
    count_stmt = apply_filters(
        select(func.count(Article.id)),
        q, language, sentiment, source_id, entity, predicate, date_from, date_to,
    )
    total = db.scalar(count_stmt) or 0

    # Result columns
    sel = select(
        Article.id,
        Article.title,
        Article.url,
        Article.source_id,
        Article.published_date,
        Article.summary,
        Article.sentiment_label,
        Article.language,
        Source.name.label("source_name"),
    ).join(Source, Source.id == Article.source_id)

    if q:
        sel = sel.add_columns(
            func.ts_rank_cd(
                Article.search_vector, func.websearch_to_tsquery("simple", q)
            ).label("rank")
        )

    sel = apply_filters(
        sel, q, language, sentiment, source_id, entity, predicate, date_from, date_to
    )

    if q and sort_mode == "rank":
        sel = sel.order_by(desc("rank"))
    else:
        sel = sel.order_by(desc(Article.discovered_at))

    sel = sel.limit(limit).offset(offset)
    rows = db.execute(sel).all()

    # Top entities per result article (single query, grouped in Python)
    article_ids = [r.id for r in rows]
    ent_map: dict[int, list[dict]] = {}
    if article_ids:
        ent_rows = db.execute(
            select(
                Entity.article_id,
                EntityNode.canonical_text,
                EntityNode.label,
            )
            .join(EntityNode, Entity.node_id == EntityNode.id)
            .where(Entity.article_id.in_(article_ids))
        ).all()
        for er in ent_rows:
            ent_map.setdefault(er.article_id, []).append(
                {"text": er.canonical_text, "label": er.label}
            )

    return {
        "total": total,
        "query": q,
        "limit": limit,
        "offset": offset,
        "results": [
            {
                "id": r.id,
                "title": r.title,
                "url": r.url,
                "source_id": r.source_id,
                "source_name": r.source_name,
                "published_date": r.published_date.isoformat() if r.published_date else None,
                "summary": r.summary,
                "sentiment_label": r.sentiment_label,
                "language": r.language,
                "rank": round(float(r.rank), 4) if q and getattr(r, "rank", None) is not None else None,
                "entities": ent_map.get(r.id, [])[:5],
            }
            for r in rows
        ],
    }
