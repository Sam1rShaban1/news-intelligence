"""Unit tests for the search query builder (no FastAPI / DB needed)."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from src.api.search_query import apply_filters, parse_list, search_base_query
from src.db.models.article import Article


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_parse_list():
    assert parse_list(None) == []
    assert parse_list("mk") == ["mk"]
    assert parse_list("mk, sq ,en") == ["mk", "sq", "en"]
    assert parse_list(["mk", "sq"]) == ["mk", "sq"]
    assert parse_list("") == []


def test_apply_filters_fulltext():
    sql = _sql(apply_filters(select(Article.id), q="corruption"))
    assert "websearch_to_tsquery" in sql
    assert "@@" in sql


def test_apply_filters_language_list():
    sql = _sql(apply_filters(select(Article.id), language="mk,sq"))
    assert "IN" in sql  # comma list -> IN clause


def test_apply_filters_sentiment_and_source():
    sql = _sql(apply_filters(select(Article.id), sentiment="neg", source_id=3))
    assert "sentiment_label" in sql
    assert "source_id" in sql


def test_apply_filters_entity_subquery():
    sql = _sql(apply_filters(select(Article.id), entity="skopje"))
    assert "entity_nodes" in sql


def test_apply_filters_predicate_subquery():
    sql = _sql(apply_filters(select(Article.id), predicate="appointed"))
    assert "relationships" in sql


def test_apply_filters_date_range():
    sql = _sql(
        apply_filters(select(Article.id), date_from=date(2026, 1, 1), date_to=date(2026, 2, 1))
    )
    assert "discovered_at" in sql


def test_search_base_query_returns_select_with_filters():
    stmt = search_base_query(q="war", language="mk", sentiment="neg")
    sql = _sql(stmt)
    assert "websearch_to_tsquery" in sql
    assert "IN" in sql
    assert "sentiment_label" in sql
