"""Stories route — event clusters derived from entity overlap (Phase 6)."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.db.models.article import Article
from src.db.models.entity_node import EntityNode
from src.db.models.source import Source
from src.db.models.story import Story, story_articles

router = APIRouter(tags=["stories"])


def _story_summary(db: Session, story_id: int) -> str | None:
    """Most informative member summary (longest non-empty)."""
    article_id = db.execute(
        select(Article.id)
        .join(story_articles, story_articles.c.article_id == Article.id)
        .where(story_articles.c.story_id == story_id, Article.summary.isnot(None))
        .order_by(func.length(Article.summary).desc())
        .limit(1)
    ).scalar()
    if article_id is None:
        return None
    return db.execute(
        select(Article.summary).where(Article.id == article_id)
    ).scalar()


@router.get("/stories")
def list_stories(
    days: int = Query(default=7, ge=1, le=90, description="Window in days"),
    language: str | None = Query(default=None, description="en|mk|sq|tr|..."),
    sentiment: str | None = Query(default=None, description="pos|neg|neutral"),
    entity: str | None = Query(default=None, description="Filter by canonical entity text (substring)"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    query = select(Story)
    if language:
        query = query.where(Story.language == language.lower())
    if sentiment:
        query = query.where(Story.dominant_sentiment == sentiment.lower())
    if entity:
        node_id = db.execute(
            select(EntityNode.id)
            .where(EntityNode.canonical_text.ilike(f"%{entity}%"))
            .limit(1)
        ).scalar()
        if node_id is None:
            return {"stories": [], "total": 0}
        query = query.where(Story.entity_node_ids.op("&&")([node_id]))
    query = query.order_by(desc(Story.last_seen)).limit(limit)
    stories = db.execute(query).scalars().all()

    out = []
    for s in stories:
        top_ids = (s.entity_node_ids or [])[:6]
        nodes = (
            db.execute(
                select(EntityNode.id, EntityNode.canonical_text, EntityNode.label).where(
                    EntityNode.id.in_(top_ids)
                )
            ).all()
            if top_ids
            else []
        )
        out.append(
            {
                "id": s.id,
                "title": s.title,
                "language": s.language,
                "dominant_sentiment": s.dominant_sentiment,
                "avg_sentiment_score": s.avg_sentiment_score,
                "member_count": s.member_count,
                "top_entities": [
                    {"id": n.id, "text": n.canonical_text, "label": n.label} for n in nodes
                ],
                "first_seen": s.first_seen.isoformat() if s.first_seen else None,
                "last_seen": s.last_seen.isoformat() if s.last_seen else None,
                "summary": _story_summary(db, s.id),
            }
        )
    return {"stories": out, "total": len(out)}


@router.get("/stories/{story_id}")
def get_story(
    story_id: int = Path(..., description="Story id"),
    db: Session = Depends(get_db),
) -> dict:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")

    rows = db.execute(
        select(
            Article.id,
            Article.title,
            Article.url,
            Article.language,
            Article.sentiment_label,
            Article.sentiment_score,
            Article.summary,
            Article.discovered_at,
            Source.name.label("source"),
        )
        .join(story_articles, story_articles.c.article_id == Article.id)
        .join(Source, Article.source_id == Source.id)
        .where(story_articles.c.story_id == story_id)
        .order_by(desc(Article.discovered_at))
    ).all()

    return {
        "id": story.id,
        "title": story.title,
        "language": story.language,
        "dominant_sentiment": story.dominant_sentiment,
        "avg_sentiment_score": story.avg_sentiment_score,
        "member_count": story.member_count,
        "first_seen": story.first_seen.isoformat() if story.first_seen else None,
        "last_seen": story.last_seen.isoformat() if story.last_seen else None,
        "members": [
            {
                "id": r.id,
                "title": r.title,
                "url": r.url,
                "language": r.language,
                "sentiment_label": r.sentiment_label,
                "sentiment_score": r.sentiment_score,
                "summary": r.summary,
                "source": r.source,
                "discovered_at": r.discovered_at.isoformat() if r.discovered_at else None,
            }
            for r in rows
        ],
    }
