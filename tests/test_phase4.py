"""Phase 4 backend tests: alerts, PDF export, semantic (embeddings) search."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.main import app
from src.db.models.alert import Alert, AlertRule
from src.db.models.article import Article
from src.db.models.entity import Entity
from src.db.models.entity_node import EntityNode
from src.db.models.source import Source
from src.db.session import SessionLocal

_client = TestClient(app)


def _source(db, name="Src", url="https://example.com/x"):
    s = Source(name=name, url=url)
    db.add(s)
    db.flush()
    return s.id


def _article(db, sid, title="T", status="analyzed", lang="en", day=0, score=None):
    a = Article(
        source_id=sid, url=f"https://e.com/{sid}/{day}/{title}", url_hash=f"u{sid}{day}{title}",
        status=status, title=title, language=lang,
        published_date=datetime(2026, 1, 1 + day, 12, 0, tzinfo=timezone.utc),
        sentiment_score=score,
    )
    db.add(a)
    db.flush()
    return a


# ---- Alerts ----------------------------------------------------------------

def test_alerts_keyword_and_sentiment():
    with SessionLocal() as db:
        sid = _source(db, name="AlertSrc", url="https://example.com/alert")
        a = _article(db, sid, "government corruption scandal", day=0, lang="en", score=-0.6)
        db.commit()
        aid = a.id

    r = _client.post(
        "/alerts/rules",
        json={"name": "Corruption", "query": "corruption", "languages": ["en"], "min_sentiment": -0.3},
    )
    assert r.status_code == 200, r.text
    rule_id = r.json()["id"]

    from src.workers.alerts_service import run_alerts_cycle
    from src.workers.lifecycle import WorkerConfig

    n = run_alerts_cycle(WorkerConfig(poll_interval=1))
    assert n >= 1

    r = _client.get("/alerts")
    assert r.status_code == 200
    body = r.json()
    assert any(al["rule"]["id"] == rule_id and al["article"]["id"] == aid for al in body["alerts"])

    alert_id = body["alerts"][0]["id"]
    r = _client.post(f"/alerts/{alert_id}/read")
    assert r.status_code == 200 and r.json()["read"] is True

    # Re-running must not create duplicates.
    assert run_alerts_cycle(WorkerConfig(poll_interval=1)) == 0

    r = _client.delete(f"/alerts/rules/{rule_id}")
    assert r.status_code == 200


def test_alerts_entity_filter():
    with SessionLocal() as db:
        sid = _source(db, name="EntSrc", url="https://example.com/ent")
        a = _article(db, sid, "minister resigns", day=0, lang="en")
        n = EntityNode(canonical_text="Jane Minister", label="PER", mention_count=1)
        db.add(n)
        db.flush()
        db.add(Entity(article_id=a.id, node_id=n.id, text="Jane Minister", label="PER", confidence=0.9))
        db.commit()
        nid, aid = n.id, a.id

    r = _client.post("/alerts/rules", json={"name": "Watch Jane", "entity_node_id": nid})
    assert r.status_code == 200
    rule_id = r.json()["id"]

    from src.workers.alerts_service import run_alerts_cycle
    from src.workers.lifecycle import WorkerConfig

    n = run_alerts_cycle(WorkerConfig(poll_interval=1))
    assert n == 1

    r = _client.get("/alerts")
    assert any(al["rule"]["id"] == rule_id for al in r.json()["alerts"])
    _client.delete(f"/alerts/rules/{rule_id}")


def test_alerts_create_validation():
    # Unknown entity node -> 404
    r = _client.post("/alerts/rules", json={"name": "X", "entity_node_id": 999999})
    assert r.status_code == 404
    # Empty name -> 400
    r = _client.post("/alerts/rules", json={"name": "  "})
    assert r.status_code == 400


# ---- PDF export ------------------------------------------------------------

def _have_reportlab():
    try:
        import reportlab  # noqa: F401

        return True
    except Exception:
        return False


def test_pdf_export_disabled_flag():
    from config.settings import settings

    old = settings.feature_pdf_export
    settings.feature_pdf_export = False
    try:
        r = _client.get("/export/articles/1/pdf")
        assert r.status_code == 503
    finally:
        settings.feature_pdf_export = old


def test_pdf_export_article():
    if not _have_reportlab():
        import pytest

        pytest.skip("reportlab not installed in this environment")
    with SessionLocal() as db:
        sid = _source(db, name="PdfSrc", url="https://example.com/pdf")
        a = _article(db, sid, "headline about policy", day=0, lang="en")
        db.commit()
        aid = a.id

    r = _client.get(f"/export/articles/{aid}/pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"

    r = _client.get(f"/export/stories/999999/pdf")
    assert r.status_code == 404
    r = _client.get(f"/export/articles/999999/pdf")
    assert r.status_code == 404


# ---- Semantic (embeddings) search ------------------------------------------

def test_semantic_search():
    with SessionLocal() as db:
        sid = _source(db, name="SemSrc", url="https://example.com/sem")
        a1 = _article(db, sid, "economy inflation prices rise", day=0, lang="en")
        a2 = _article(db, sid, "sports football match result", day=1, lang="en")
        db.commit()
        aid1 = a1.id

    from src.workers.embeddings_service import run_embeddings_cycle
    from src.workers.lifecycle import WorkerConfig

    assert run_embeddings_cycle(WorkerConfig(poll_interval=1)) >= 2

    r = _client.post("/search/semantic", json={"text": "inflation economy", "limit": 5})
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert results
    assert results[0]["id"] == aid1


def test_semantic_search_disabled_and_short():
    from config.settings import settings

    old = settings.feature_embeddings
    settings.feature_embeddings = False
    try:
        r = _client.post("/search/semantic", json={"text": "x"})
        assert r.status_code == 503
    finally:
        settings.feature_embeddings = old

    r = _client.post("/search/semantic", json={"text": "a"})
    assert r.status_code == 400

