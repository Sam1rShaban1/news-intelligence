"""Entities route — search and browse extracted named entities + canonical nodes."""

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.db.models.entity import Entity
from src.db.models.entity_node import EntityNode

router = APIRouter(tags=["entities"])


@router.get("/entities")
def list_entities(
    label: str | None = Query(default=None, description="Filter by label: PER, ORG, LOC"),
    q: str | None = Query(default=None, description="Search entity text"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """List extracted entities with optional filtering."""
    query = select(Entity)
    count_query = select(func.count(Entity.id))

    if label:
        query = query.where(Entity.label == label.upper())
        count_query = count_query.where(Entity.label == label.upper())

    if q:
        query = query.where(Entity.text.ilike(f"%{q}%"))
        count_query = count_query.where(Entity.text.ilike(f"%{q}%"))

    total = db.scalar(count_query) or 0
    rows = db.execute(
        query.order_by(desc(Entity.created_at)).limit(limit).offset(offset)
    ).scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "entities": [
            {
                "id": e.id,
                "text": e.text,
                "label": e.label,
                "confidence": e.confidence,
                "article_id": e.article_id,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in rows
        ],
    }


@router.get("/entities/top")
def top_entities(
    label: str | None = Query(default=None, description="Filter by label"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """Most frequently mentioned entities."""
    query = (
        select(
            Entity.text,
            Entity.label,
            func.count(Entity.id).label("count"),
        )
        .group_by(Entity.text, Entity.label)
    )

    if label:
        query = query.where(Entity.label == label.upper())

    query = query.order_by(desc("count")).limit(limit)
    rows = db.execute(query).all()

    return {
        "entities": [
            {"text": r.text, "label": r.label, "count": r.count}
            for r in rows
        ],
    }


@router.get("/entities/stats")
def entity_stats(db: Session = Depends(get_db)) -> dict:
    """Entity counts by label."""
    rows = db.execute(
        select(Entity.label, func.count(Entity.id).label("count"))
        .group_by(Entity.label)
        .order_by(desc("count"))
    ).all()

    return {
        "stats": {r.label: r.count for r in rows},
        "total": sum(r.count for r in rows),
    }


@router.get("/entities/nodes")
def list_entity_nodes(
    label: str | None = Query(default=None, description="Filter by label: PER, ORG, LOC"),
    q: str | None = Query(default=None, description="Search canonical entity text"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Canonical (deduplicated) entities, ranked by mention count."""
    query = select(EntityNode)
    count_query = select(func.count(EntityNode.id))

    if label:
        query = query.where(EntityNode.label == label.upper())
        count_query = count_query.where(EntityNode.label == label.upper())

    if q:
        query = query.where(EntityNode.canonical_text.ilike(f"%{q}%"))
        count_query = count_query.where(EntityNode.canonical_text.ilike(f"%{q}%"))

    total = db.scalar(count_query) or 0
    rows = db.execute(
        query.order_by(desc(EntityNode.mention_count)).limit(limit).offset(offset)
    ).scalars().all()

    return {
        "total": total,
        "nodes": [
            {
                "id": n.id,
                "text": n.canonical_text,
                "label": n.label,
                "mention_count": n.mention_count,
                "aliases": n.aliases or [],
            }
            for n in rows
        ],
    }


@router.get("/entities/{node_id}/articles")
def node_articles(
    node_id: int = Path(..., description="EntityNode id"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """Articles that mention a given canonical entity."""
    from src.db.models.article import Article

    query = (
        select(
            Article.id,
            Article.title,
            Article.url,
            Article.sentiment_label,
            Article.language,
            Article.published_date,
        )
        .join(Entity, Entity.article_id == Article.id)
        .where(Entity.node_id == node_id)
        .order_by(desc(Article.discovered_at))
        .limit(limit)
    )
    rows = db.execute(query).all()

    return {
        "node_id": node_id,
        "articles": [
            {
                "id": r.id,
                "title": r.title,
                "url": r.url,
                "sentiment_label": r.sentiment_label,
                "language": r.language,
                "published_date": r.published_date.isoformat() if r.published_date else None,
            }
            for r in rows
        ],
    }
