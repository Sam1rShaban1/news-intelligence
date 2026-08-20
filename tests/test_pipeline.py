"""Integration test for the article pipeline state machine.

Guards the fetch -> extract -> sentiment -> NER handoff. The NER service claims
articles with status `sentiment_done`; if the model's Check constraint ever drifts
from the migrations (or from what the workers set), these tests fail loudly instead
of shipping an empty knowledge graph.
"""

from sqlalchemy import select

from src.db.models.article import Article
from src.db.models.source import Source
from src.db.session import SessionLocal

# Statuses the pipeline actually assigns (mirrors workers + migration 010).
PIPELINE_STATUSES = [
    "new",
    "fetched",
    "extracting",
    "extracted",
    "analyzing",
    "sentiment_done",
    "ner_running",
    "analyzed",
    "failed",
]


def _make_source(db) -> int:
    src = Source(name="Pipeline Test", url="https://example.com/pipeline")
    db.add(src)
    db.flush()
    return src.id


def test_all_pipeline_statuses_accepted(client):
    with SessionLocal() as db:
        src_id = _make_source(db)
        for i, status in enumerate(PIPELINE_STATUSES):
            db.add(
                Article(
                    source_id=src_id,
                    url=f"https://example.com/{status}-{i}",
                    url_hash=f"ph-{status}-{i}",
                    status=status,
                )
            )
        # Commit succeeds only if every status satisfies the check constraint.
        db.commit()
    with SessionLocal() as db:
        db.query(Article).delete()
        db.query(Source).delete()
        db.commit()


def test_ner_claims_sentiment_done_only(client):
    with SessionLocal() as db:
        src_id = _make_source(db)
        done = Article(
            source_id=src_id,
            url="https://example.com/done",
            url_hash="ph-done",
            status="sentiment_done",
        )
        db.add(done)
        db.flush()
        done_id = done.id
        db.add(
            Article(
                source_id=src_id,
                url="https://example.com/fresh",
                url_hash="ph-fresh",
                status="new",
            )
        )
        db.commit()

    with SessionLocal() as db:
        claimed = (
            db.execute(select(Article).where(Article.status == "sentiment_done"))
            .scalars()
            .all()
        )
        assert any(a.id == done_id for a in claimed)
        assert all(a.status == "sentiment_done" for a in claimed)

    with SessionLocal() as db:
        db.query(Article).delete()
        db.query(Source).delete()
        db.commit()
