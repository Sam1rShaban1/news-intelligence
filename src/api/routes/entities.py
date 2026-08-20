"""Entities route — search and browse extracted named entities + canonical nodes."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.db.models.article import Article
from src.db.models.entity import Entity
from src.db.models.entity_edge import EntityEdge
from src.db.models.entity_node import EntityNode
from src.db.models.source import Source

router = APIRouter(tags=["entities"])


@router.get("/entities/nodes/{node_id}")
def get_entity_node(
    node_id: int = Path(..., description="EntityNode id"),
    db: Session = Depends(get_db),
) -> dict:
    """Canonical entity node details, including any Wikidata link."""
    node = db.get(EntityNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="entity node not found")
    return {
        "id": node.id,
        "canonical_text": node.canonical_text,
        "label": node.label,
        "mention_count": node.mention_count,
        "wikidata_id": node.wikidata_id,
        "description": node.description,
        "external_ids": node.external_ids,
        "wikidata_url": (
            f"https://www.wikidata.org/wiki/{node.wikidata_id}"
            if node.wikidata_id
            else None
        ),
    }


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
            Source.name.label("source_name"),
        )
        .join(Entity, Entity.article_id == Article.id)
        .join(Source, Source.id == Article.source_id)
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
                "source_name": r.source_name,
                "published_date": r.published_date.isoformat() if r.published_date else None,
            }
            for r in rows
        ],
    }


@router.get("/entities/nodes/{node_id}/dossier")
def entity_dossier(
    node_id: int = Path(..., description="EntityNode id"),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """Journalist dossier for a canonical entity: mentions, sentiment/language mix,
    top co-mentioned entities, and the most recent articles about it."""
    node = db.get(EntityNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="entity node not found")

    # Sentiment / language / date distribution over non-failed, non-duplicate articles.
    dist = db.execute(
        select(
            func.count(Article.id).label("c"),
            func.min(Article.discovered_at).label("first_seen"),
            func.max(Article.discovered_at).label("last_seen"),
        )
        .join(Entity, Entity.article_id == Article.id)
        .where(Entity.node_id == node_id, Article.status.notin_(["failed", "duplicate"]))
    ).first()

    # Recent articles mentioning this entity.
    rows = db.execute(
        select(
            Article.id,
            Article.title,
            Article.url,
            Article.sentiment_label,
            Article.language,
            Article.published_date,
            Article.discovered_at,
            Source.name.label("source_name"),
        )
        .join(Entity, Entity.article_id == Article.id)
        .join(Source, Source.id == Article.source_id)
        .where(Entity.node_id == node_id, Article.status.notin_(["failed", "duplicate"]))
        .order_by(desc(Article.discovered_at))
        .limit(limit)
    ).all()

    # Top co-mentioned entities (co-occurrence edges touching this node).
    edges = db.execute(
        select(EntityEdge)
        .where(or_(EntityEdge.node_a_id == node_id, EntityEdge.node_b_id == node_id))
        .order_by(desc(EntityEdge.weight))
        .limit(15)
    ).scalars().all()
    other_ids = [
        e.node_b_id if e.node_a_id == node_id else e.node_a_id for e in edges
    ]
    related_nodes = (
        db.execute(select(EntityNode).where(EntityNode.id.in_(other_ids))).scalars().all()
        if other_ids
        else []
    )
    related_map = {n.id: n for n in related_nodes}
    related = [
        {
            "node_id": oid,
            "text": related_map[oid].canonical_text,
            "label": related_map[oid].label,
            "weight": next(
                e.weight for e in edges
                if (e.node_a_id == node_id and e.node_b_id == oid)
                or (e.node_b_id == node_id and e.node_a_id == oid)
            ),
        }
        for oid in other_ids
        if oid in related_map
    ]

    agg = db.execute(
        select(
            Article.sentiment_label,
            Article.language,
            func.count(Article.id).label("c"),
        )
        .join(Entity, Entity.article_id == Article.id)
        .where(Entity.node_id == node_id, Article.status.notin_(["failed", "duplicate"]))
        .group_by(Article.sentiment_label, Article.language)
    ).all()
    sent: dict[str, int] = {}
    langs: dict[str, int] = {}
    for r in agg:
        if r.sentiment_label:
            sent[r.sentiment_label] = sent.get(r.sentiment_label, 0) + r.c
        if r.language:
            langs[r.language] = langs.get(r.language, 0) + r.c

    return {
        "node_id": node.id,
        "entity": {
            "text": node.canonical_text,
            "label": node.label,
            "mention_count": node.mention_count,
            "aliases": node.aliases or [],
            "wikidata_id": node.wikidata_id,
            "description": node.description,
            "wikidata_url": (
                f"https://www.wikidata.org/wiki/{node.wikidata_id}"
                if node.wikidata_id
                else None
            ),
        },
        "mentions": dist.c if dist else 0,
        "first_seen": dist.first_seen.isoformat() if dist and dist.first_seen else None,
        "last_seen": dist.last_seen.isoformat() if dist and dist.last_seen else None,
        "sentiment_distribution": sent,
        "language_distribution": langs,
        "related_entities": related,
        "recent_articles": [
            {
                "id": r.id,
                "title": r.title,
                "url": r.url,
                "sentiment_label": r.sentiment_label,
                "language": r.language,
                "source_name": r.source_name,
                "published_date": r.published_date.isoformat() if r.published_date else None,
                "discovered_at": r.discovered_at.isoformat() if r.discovered_at else None,
            }
            for r in rows
        ],
    }
