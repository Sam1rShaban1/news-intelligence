"""Reusable search/filter query builder (no FastAPI dependency, unit-testable)."""

from datetime import date, datetime

from sqlalchemy import func, select

from src.db.models.article import Article
from src.db.models.entity import Entity
from src.db.models.entity_node import EntityNode
from src.db.models.relationship import Relationship
from src.nlp.normalize import normalize_text


def parse_list(value) -> list[str]:
    """Parse a comma/space separated string (or list) into a clean list of tokens."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        value = ",".join(str(v) for v in value)
    return [v.strip() for v in str(value).split(",") if v.strip()]


def apply_filters(
    stmt,
    q: str | None = None,
    language: str | None = None,
    sentiment: str | None = None,
    source_id: int | None = None,
    entity: str | None = None,
    predicate: str | None = None,
    date_from=None,
    date_to=None,
):
    """Apply the shared set of search filters to any select rooted on `Article`."""
    if q:
        norm_q = normalize_text(q)
        if norm_q:
            ts = func.websearch_to_tsquery("simple", norm_q)
            stmt = stmt.where(Article.search_vector.op("@@")(ts))

    langs = parse_list(language)
    if langs:
        stmt = stmt.where(Article.language.in_(langs))
    sents = parse_list(sentiment)
    if sents:
        stmt = stmt.where(Article.sentiment_label.in_(sents))

    if source_id is not None:
        stmt = stmt.where(Article.source_id == source_id)

    if entity:
        sub = (
            select(Entity.article_id)
            .join(EntityNode, Entity.node_id == EntityNode.id)
            .where(EntityNode.canonical_text == entity)
        )
        stmt = stmt.where(Article.id.in_(sub))

    if predicate:
        sub = select(Relationship.article_id).where(Relationship.predicate == predicate)
        stmt = stmt.where(Article.id.in_(sub))

    if date_from is not None:
        stmt = stmt.where(Article.discovered_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(Article.discovered_at <= date_to)

    # Never surface failed / duplicate (near-duplicate) articles.
    stmt = stmt.where(Article.status.notin_(["failed", "duplicate"]))
    return stmt


def search_base_query(
    q: str | None = None,
    language: str | None = None,
    sentiment: str | None = None,
    source_id: int | None = None,
    entity: str | None = None,
    predicate: str | None = None,
    date_from: date | datetime | None = None,
    date_to: date | datetime | None = None,
):
    """Return a `select(Article.id)` already carrying all shared filters."""
    return apply_filters(
        select(Article.id), q, language, sentiment, source_id, entity, predicate, date_from, date_to
    )
