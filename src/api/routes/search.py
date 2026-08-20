"""Search route — PostgreSQL full-text search across articles with filters."""

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from config.settings import settings
from src.api.deps import get_db
from src.api.search_query import apply_filters
from src.db.models.article import Article
from src.db.models.entity import Entity
from src.db.models.entity_node import EntityNode
from src.db.models.source import Source
from src.nlp.embeddings import cosine, get_embedder
from src.nlp.normalize import normalize_text

router = APIRouter(tags=["search"])


class SemanticQuery(BaseModel):
    text: str
    limit: int = 20
    language: str | None = None


@router.get("/search")
def search_articles(
    q: str | None = Query(default=None, min_length=2, description="Full-text query"),
    language: str | None = Query(
        default=None, description="Comma-separated languages (mk,sq,en,tr)",
    ),
    sentiment: str | None = Query(default=None, description="Comma-separated pos/neg/neutral"),
    source_id: int | None = Query(default=None, description="Filter by source id"),
    entity: str | None = Query(
        default=None, description="Only articles mentioning this entity (canonical text)",
    ),
    predicate: str | None = Query(
        default=None, description="Only articles with a relationship of this predicate",
    ),
    date_from: date | None = Query(
        default=None, description="Articles discovered on/after this date",
    ),
    date_to: date | None = Query(
        default=None, description="Articles discovered on/before this date",
    ),
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
        norm_q = normalize_text(q)
        if norm_q:
            rank_expr = func.ts_rank(
                Article.search_vector, func.websearch_to_tsquery("simple", norm_q)
            )
        else:
            rank_expr = func.literal(0.0)
        sel = sel.add_columns(rank_expr.label("rank"))

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
                "rank": (
                    round(float(r.rank), 4)
                    if q and getattr(r, "rank", None) is not None
                    else None
                ),
                "entities": ent_map.get(r.id, [])[:5],
            }
            for r in rows
        ],
    }


@router.post("/search/semantic", response_model=None)
def semantic_search(body: SemanticQuery, db: Session = Depends(get_db)) -> dict:
    """Nearest-neighbour search over precomputed article embeddings (VPS tier).

    Returns analyzed articles most similar to `text` by cosine similarity. Requires
    embeddings to have been computed by the embeddings worker (FEATURE_EMBEDDINGS).
    """
    if not settings.feature_embeddings:
        raise HTTPException(
            status_code=503, detail="Semantic search is disabled (FEATURE_EMBEDDINGS=false)"
        )
    q = (body.text or "").strip()
    if len(q) < 2:
        raise HTTPException(status_code=400, detail="Query too short")

    embedder = get_embedder()
    qvec = embedder.embed([q])[0]

    rows = db.execute(
        select(Article, Source.name.label("source_name"))
        .join(Source, Source.id == Article.source_id)
        .where(Article.status == "analyzed", Article.embedding.isnot(None))
    ).all()

    scored = []
    for a, source_name in rows:
        if body.language and a.language != body.language:
            continue
        sim = cosine(qvec, a.embedding)
        if sim <= 0:
            continue
        scored.append((sim, a, source_name))
    scored.sort(key=lambda x: -x[0])
    top = scored[: body.limit]

    return {
        "query": q,
        "count": len(top),
        "results": [
            {
                "id": a.id,
                "title": a.title,
                "url": a.url,
                "source_id": a.source_id,
                "source_name": source_name,
                "language": a.language,
                "sentiment_label": a.sentiment_label,
                "published_date": a.published_date.isoformat() if a.published_date else None,
                "summary": a.summary,
                "score": round(sim, 4),
            }
            for sim, a, source_name in top
        ],
    }
