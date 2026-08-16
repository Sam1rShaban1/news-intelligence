"""Stories route — event clusters derived from entity overlap (Phase 6)."""

from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.db.models.article import Article
from src.db.models.entity_node import EntityNode
from src.db.models.source import Source
from src.db.models.story import Story, story_articles

router = APIRouter(tags=["stories"])


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
    if not stories:
        return {"stories": [], "total": 0}

    story_ids = [s.id for s in stories]
    node_id_sets = {s.id: list(s.entity_node_ids or [])[:6] for s in stories}
    all_node_ids = sorted({nid for ids in node_id_sets.values() for nid in ids})

    # 1) All top entities in a single IN lookup (was one query per story).
    nodes = (
        db.execute(
            select(EntityNode.id, EntityNode.canonical_text, EntityNode.label).where(
                EntityNode.id.in_(all_node_ids)
            )
        ).all()
        if all_node_ids
        else []
    )
    node_map = {n.id: {"id": n.id, "text": n.canonical_text, "label": n.label} for n in nodes}

    # 2) Longest summary per story (DISTINCT ON).
    summary_rows = (
        db.execute(
            select(Article.summary, story_articles.c.story_id)
            .select_from(story_articles)
            .join(Article, Article.id == story_articles.c.article_id)
            .where(story_articles.c.story_id.in_(story_ids), Article.summary.isnot(None))
            .order_by(story_articles.c.story_id, func.length(Article.summary).desc())
            .distinct(story_articles.c.story_id)
        )
        .all()
    )
    summary_map = {r.story_id: r.summary for r in summary_rows}

    # 3) Dominant sentiment / language per story (single grouped query). This also
    #    fixes live stories whose stored aggregates are still None (incremental path).
    agg_rows = (
        db.execute(
            select(
                story_articles.c.story_id,
                Article.sentiment_label,
                Article.language,
                func.count().label("c"),
            )
            .select_from(story_articles)
            .join(Article, Article.id == story_articles.c.article_id)
            .where(story_articles.c.story_id.in_(story_ids))
            .group_by(story_articles.c.story_id, Article.sentiment_label, Article.language)
        )
        .all()
    )
    sent_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    lang_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in agg_rows:
        if r.sentiment_label:
            sent_counts[r.story_id][r.sentiment_label] += r.c
        if r.language:
            lang_counts[r.story_id][r.language] += r.c

    out = []
    for s in stories:
        top_ids = node_id_sets[s.id]
        top_entities = [node_map[nid] for nid in top_ids if nid in node_map]
        dom_sent = (
            max(sent_counts[s.id].items(), key=lambda kv: kv[1])[0]
            if sent_counts[s.id]
            else s.dominant_sentiment
        )
        lang = (
            max(lang_counts[s.id].items(), key=lambda kv: kv[1])[0]
            if lang_counts[s.id]
            else s.language
        )
        out.append(
            {
                "id": s.id,
                "title": s.title,
                "language": lang,
                "dominant_sentiment": dom_sent,
                "avg_sentiment_score": s.avg_sentiment_score,
                "member_count": s.member_count,
                "top_entities": top_entities,
                "first_seen": s.first_seen.isoformat() if s.first_seen else None,
                "last_seen": s.last_seen.isoformat() if s.last_seen else None,
                "summary": summary_map.get(s.id),
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
