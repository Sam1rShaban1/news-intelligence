"""Analytics route — trend data for the dashboard (sentiment over time, language
mix, trending entities). Computed from existing article/entity columns."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.db.models.article import Article
from src.db.models.entity import Entity
from src.db.models.entity_node import EntityNode

router = APIRouter(tags=["analytics"])


@router.get("/analytics/overview")
def analytics_overview(
    days: int = Query(default=30, ge=1, le=365),
    interval: str = Query(default="day", description="day | week | month"),
    language: str | None = Query(default=None, description="Restrict to a language"),
    db: Session = Depends(get_db),
) -> dict:
    """Aggregated trends over the last `days`."""
    if interval not in ("day", "week", "month"):
        interval = "day"
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # ── Sentiment over time ──────────────────────────────────
    sot = (
        select(
            func.date_trunc(interval, Article.discovered_at).label("bucket"),
            Article.sentiment_label,
            func.count(Article.id).label("cnt"),
            func.coalesce(func.avg(Article.sentiment_score), 0.0).label("avg_score"),
        )
        .where(Article.sentiment_label.isnot(None), Article.discovered_at >= cutoff)
    )
    if language:
        sot = sot.where(Article.language == language)
    sot = sot.where(Article.status.notin_(["failed", "duplicate"]))
    sot = sot.group_by("bucket", Article.sentiment_label).order_by("bucket")
    sot_rows = db.execute(sot).all()

    sentiment_over_time: dict[str, dict] = {}
    for r in sot_rows:
        bucket = r.bucket.isoformat() if r.bucket else None
        sentiment_over_time.setdefault(
            bucket, {"bucket": bucket, "pos": 0, "neg": 0, "neutral": 0, "avg_score": 0.0}
        )
        sentiment_over_time[bucket][r.sentiment_label] = r.cnt
        sentiment_over_time[bucket]["avg_score"] = round(float(r.avg_score), 4)

    # ── Language mix over time ──────────────────────────────
    lm = (
        select(
            func.date_trunc(interval, Article.discovered_at).label("bucket"),
            Article.language,
            func.count(Article.id).label("cnt"),
        )
        .where(Article.discovered_at >= cutoff)
    )
    if language:
        lm = lm.where(Article.language == language)
    lm = lm.where(Article.status.notin_(["failed", "duplicate"]))
    lm = lm.group_by("bucket", Article.language).order_by("bucket")
    lm_rows = db.execute(lm).all()

    language_mix: dict[str, dict] = {}
    for r in lm_rows:
        bucket = r.bucket.isoformat() if r.bucket else None
        language_mix.setdefault(bucket, {"bucket": bucket})
        language_mix[bucket][r.language or "und"] = r.cnt

    # ── Trending entities (most mentioned in window) ────────
    te = (
        select(
            EntityNode.canonical_text,
            EntityNode.label,
            func.count(Entity.id).label("mentions"),
        )
        .join(Entity, Entity.node_id == EntityNode.id)
        .join(Article, Entity.article_id == Article.id)
        .where(Article.discovered_at >= cutoff)
    )
    if language:
        te = te.where(Article.language == language)
    te = te.group_by(EntityNode.id).order_by(desc("mentions")).limit(20)
    te_rows = db.execute(te).all()

    return {
        "days": days,
        "interval": interval,
        "sentiment_over_time": list(sentiment_over_time.values()),
        "language_mix": list(language_mix.values()),
        "trending_entities": [
            {"text": r.canonical_text, "label": r.label, "mentions": r.mentions}
            for r in te_rows
        ],
    }
