"""Near-duplicate detection: content_hash dedup + search/analytics exclusion."""

from fastapi.testclient import TestClient
from sqlalchemy import func

from src.api.main import app
from src.collector.dedup import compute_content_hash
from src.db.models.article import Article
from src.db.models.source import Source
from src.db.session import SessionLocal
from src.nlp.normalize import normalize_text
from src.workers.extract import find_duplicate

_client = TestClient(app)

BODY = "Identical article body ingested from two different outlets."


def _make_source(db):
    src = Source(name="Dedup", url="https://example.com/dedup")
    db.add(src)
    db.flush()
    return src.id


def test_find_duplicate_returns_processed_twin():
    with SessionLocal() as db:
        sid = _make_source(db)
        ch = compute_content_hash(BODY)
        canonical = Article(
            source_id=sid, url="https://a.com/1", url_hash="dup-a", status="analyzed",
            content=BODY, content_hash=ch,
        )
        twin = Article(
            source_id=sid, url="https://b.com/1", url_hash="dup-b", status="new",
            content=BODY, content_hash=ch,
        )
        db.add_all([canonical, twin])
        db.commit()
        cid, tid = canonical.id, twin.id

    with SessionLocal() as db:
        assert find_duplicate(db, tid, ch) == cid
        # The canonical itself is not its own duplicate.
        assert find_duplicate(db, cid, ch) is None


def test_search_excludes_duplicate_articles():
    with SessionLocal() as db:
        sid = _make_source(db)
        good = Article(
            source_id=sid, url="https://g.com/1", url_hash="ded-g", status="analyzed",
            title="unique story here", language="en",
        )
        good.search_vector = func.to_tsvector("simple", normalize_text("unique story here"))
        dup = Article(
            source_id=sid, url="https://g.com/2", url_hash="ded-d", status="duplicate",
            title="unique story here", language="en",
        )
        dup.search_vector = func.to_tsvector("simple", normalize_text("unique story here"))
        db.add_all([good, dup])
        db.commit()
        gid, did = good.id, dup.id

    r = _client.get("/search", params={"q": "unique"})
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()["results"]]
    assert gid in ids
    # The duplicate article must not appear in search results.
    assert did not in ids
