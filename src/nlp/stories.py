"""Story / event clustering from article entity overlap.

Phase 6. Groups articles that share entities within a recent time window into
"stories" so the knowledge graph resolves into actual narratives. Lightweight:
no new model — uses Jaccard overlap of canonical entity-node id sets.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from src.db.models.article import Article
from src.db.models.entity import Entity
from src.db.models.story import Story, story_articles

logger = logging.getLogger(__name__)

STORY_WINDOW_DAYS = 7
STORY_JACCARD_THRESHOLD = 0.5
# Require at least this many shared canonical entities, otherwise two articles that
# merely overlap on a single entity (Jaccard can still be high for tiny sets) are kept
# as separate stories.
STORY_MIN_SHARED_ENTITIES = 2


def article_entity_ids(session, article_id: int) -> set[int]:
    """Canonical entity-node ids mentioned by this article."""
    rows = session.execute(
        select(Entity.node_id).where(
            Entity.article_id == article_id, Entity.node_id.isnot(None)
        )
    ).scalars().all()
    return set(int(r) for r in rows)


def score_match(art_ids: set[int], story_ids: set[int]) -> float:
    """Jaccard similarity between two entity-id sets."""
    if not art_ids or not story_ids:
        return 0.0
    inter = art_ids & story_ids
    union = art_ids | story_ids
    return len(inter) / len(union)


def select_story(
    art_ids: set[int],
    candidates: list[Story],
    threshold: float = STORY_JACCARD_THRESHOLD,
    min_shared: int = STORY_MIN_SHARED_ENTITIES,
) -> Story | None:
    """Pick the best-matching candidate story above `threshold` with enough shared
    entities, else None.

    Both gates must hold: Jaccard similarity >= `threshold` AND at least
    `min_shared` canonical entities in common. The second gate stops two articles
    that share only one entity (which can still yield a high Jaccard on tiny sets)
    from being merged into one story.
    """
    best: Story | None = None
    best_score = 0.0
    for s in candidates:
        s_ids = set(s.entity_node_ids or [])
        sc = score_match(art_ids, s_ids)
        shared = len(art_ids & s_ids)
        if sc >= threshold and shared >= min_shared and sc > best_score:
            best, best_score = s, sc
    return best


def _recompute(session, story: Story) -> None:
    """Refresh aggregate fields from member articles + union entity ids."""
    info = session.execute(
        select(
            func.count(Article.id).label("n"),
            func.avg(Article.sentiment_score).label("avg_score"),
            func.min(Article.discovered_at).label("first_seen"),
            func.max(Article.discovered_at).label("last_seen"),
        )
        .join(story_articles, story_articles.c.article_id == Article.id)
        .where(story_articles.c.story_id == story.id)
    ).one()

    dom = session.execute(
        select(Article.sentiment_label, func.count().label("c"))
        .join(story_articles, story_articles.c.article_id == Article.id)
        .where(
            story_articles.c.story_id == story.id,
            Article.sentiment_label.isnot(None),
        )
        .group_by(Article.sentiment_label)
        .order_by(func.count().desc())
        .limit(1)
    ).first()
    lang = session.execute(
        select(Article.language, func.count().label("c"))
        .join(story_articles, story_articles.c.article_id == Article.id)
        .where(story_articles.c.story_id == story.id, Article.language.isnot(None))
        .group_by(Article.language)
        .order_by(func.count().desc())
        .limit(1)
    ).first()

    ids = session.execute(
        select(func.array_agg(func.distinct(Entity.node_id)))
        .join(story_articles, story_articles.c.article_id == Entity.article_id)
        .where(story_articles.c.story_id == story.id, Entity.node_id.isnot(None))
    ).scalar()

    story.member_count = int(info.n or 0)
    story.avg_sentiment_score = float(info.avg_score) if info.avg_score is not None else None
    story.dominant_sentiment = dom[0] if dom else None
    story.language = lang[0] if lang else None
    story.first_seen = info.first_seen
    story.last_seen = info.last_seen
    story.entity_node_ids = sorted(set(int(x) for x in (ids or [])))


def assign_story(session, article: Article, recompute: bool = True) -> Story | None:
    """Attach `article` to an existing story or create a new one. Returns it.

    With `recompute=False` (the live NER path) the aggregate fields are updated
    incrementally — O(1) per article — instead of re-aggregating all members,
    which keeps the NER stage cheap at scale. `recompute=True` (backfill) does a
    full refresh and is also used to fix dominant_sentiment/language/avg score.
    """
    art_ids = article_entity_ids(session, article.id)
    if not art_ids:
        return None

    window = datetime.now(timezone.utc) - timedelta(days=STORY_WINDOW_DAYS)
    candidates = session.execute(
        select(Story).where(
            Story.entity_node_ids.op("&&")(list(art_ids)),
            Story.last_seen >= window,
        )
    ).scalars().all()

    story = select_story(art_ids, candidates, STORY_JACCARD_THRESHOLD)
    if story is None:
        story = Story(title=article.title or article.url)
        session.add(story)
        session.flush()

    already = session.execute(
        select(story_articles.c.article_id).where(
            story_articles.c.story_id == story.id,
            story_articles.c.article_id == article.id,
        )
    ).scalar()

    if already is None:
        session.execute(
            story_articles.insert().values(
                story_id=story.id, article_id=article.id
            )
        )
        # Incremental aggregate update (no full re-aggregation).
        story.member_count = (story.member_count or 0) + 1
        disc = article.discovered_at or datetime.now(timezone.utc)
        if story.first_seen is None or disc < story.first_seen:
            story.first_seen = disc
        if story.last_seen is None or disc > story.last_seen:
            story.last_seen = disc
        base = set(int(x) for x in (story.entity_node_ids or []))
        story.entity_node_ids = sorted(base | art_ids)
        if article.sentiment_score is not None:
            n = story.member_count
            prev = story.avg_sentiment_score or 0.0
            story.avg_sentiment_score = round((prev * (n - 1) + article.sentiment_score) / n, 4)

    if recompute:
        _recompute(session, story)

    session.flush()
    return story


def backfill_stories(limit: int | None = None) -> int:
    """Cluster all already-`analyzed` articles (one-off / after deploy)."""
    from src.db.session import SessionLocal

    count = 0
    with SessionLocal() as session:
        query = (
            select(Article)
            .where(Article.status == "analyzed")
            .order_by(Article.analyzed_at)
        )
        if limit:
            query = query.limit(limit)
        articles = session.execute(query).scalars().all()
        for art in articles:
            assign_story(session, art)
            count += 1
            if count % 50 == 0:
                session.commit()
        session.commit()
    logger.info("Backfilled stories for %d articles", count)
    return count
