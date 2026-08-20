"""Phase 3 lightweight journalist features: export, dossier, timeline, watchlist, credibility."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func

from src.api.main import app
from src.db.models.article import Article
from src.db.models.entity import Entity
from src.db.models.entity_node import EntityNode
from src.db.models.source import Source
from src.db.models.story import Story
from src.db.models.watchlist import WatchlistItem
from src.db.session import SessionLocal
from src.nlp.normalize import normalize_text

_client = TestClient(app)


def _source(db, name="Src", url="https://example.com/x"):
    s = Source(name=name, url=url)
    db.add(s)
    db.flush()
    return s.id


def _article(db, sid, title="T", status="analyzed", lang="en", body="news update today", day=0):
    a = Article(
        source_id=sid, url=f"https://e.com/{sid}/{day}/{title}", url_hash=f"u{sid}{day}{title}",
        status=status, title=title, language=lang,
        published_date=datetime(2026, 1, 1 + day, 12, 0, tzinfo=timezone.utc),
    )
    a.search_vector = func.to_tsvector("simple", normalize_text(title + " " + body))
    db.add(a)
    db.flush()
    return a


# ---- Export ----------------------------------------------------------------

def test_export_articles_json_and_csv():
    with SessionLocal() as db:
        sid = _source(db)
        _article(db, sid, "alpha report", day=0)
        _article(db, sid, "beta report", day=1)
        db.commit()

    r = _client.get("/export/articles", params={"format": "json"})
    assert r.status_code == 200
    assert r.json()["total"] == 2

    r = _client.get("/export/articles", params={"format": "csv"})
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "title,url" in r.text.splitlines()[0]
    assert "alpha report" in r.text


def test_export_search_csv():
    with SessionLocal() as db:
        sid = _source(db)
        _article(db, sid, "election coverage", day=0)
        db.commit()
    r = _client.get("/export/search", params={"q": "election", "format": "csv"})
    assert r.status_code == 200
    assert "election coverage" in r.text


def test_export_story_csv():
    with SessionLocal() as db:
        sid = _source(db)
        a = _article(db, sid, "story item", day=0)
        s = Story(title="My story", member_count=1)
        db.add(s)
        db.flush()
        s.members.append(a)
        db.commit()
        sid_ = s.id

    r = _client.get(f"/export/stories/{sid_}", params={"format": "csv"})
    assert r.status_code == 200
    assert "story item" in r.text


# ---- Entity dossier --------------------------------------------------------

def test_entity_dossier():
    with SessionLocal() as db:
        sid = _source(db)
        a = _article(db, sid, "minister speech", day=0, lang="en")
        n = EntityNode(canonical_text="Jane Minister", label="PER", mention_count=2,
                       wikidata_id="Q42")
        db.add(n)
        db.flush()
        db.add(
            Entity(
                article_id=a.id, node_id=n.id,
                text="Jane Minister", label="PER", confidence=0.9,
            )
        )
        db.commit()
        nid = n.id

    r = _client.get(f"/entities/nodes/{nid}/dossier")
    assert r.status_code == 200
    body = r.json()
    assert body["entity"]["text"] == "Jane Minister"
    assert body["entity"]["wikidata_id"] == "Q42"
    assert body["mentions"] == 1
    assert len(body["recent_articles"]) == 1


# ---- Story timeline --------------------------------------------------------

def test_story_timeline():
    with SessionLocal() as db:
        sid = _source(db)
        a1 = _article(db, sid, "day one", day=0, lang="en")
        a2 = _article(db, sid, "day two", day=1, lang="en")
        s = Story(title="Timeline story", member_count=2)
        db.add(s)
        db.flush()
        s.members.append(a1)
        s.members.append(a2)
        db.commit()
        sid_ = s.id

    r = _client.get(f"/stories/{sid_}/timeline")
    assert r.status_code == 200
    body = r.json()
    assert body["member_count"] == 2
    assert len(body["articles"]) == 2
    # Articles ordered chronologically (oldest first).
    dates = [x["published_date"] for x in body["articles"]]
    assert dates == sorted(dates)
    assert len(body["timeline"]) >= 1


# ---- Watchlist -------------------------------------------------------------

def test_watchlist_crud():
    with SessionLocal() as db:
        n = EntityNode(canonical_text="Watch Me", label="ORG", mention_count=1)
        db.add(n)
        db.flush()
        nid = n.id
        db.commit()
        assert db.get(WatchlistItem, nid) is None

    # Add
    r = _client.post("/watchlist", json={"node_id": nid, "note": "track"})
    assert r.status_code == 200
    assert r.json()["node_id"] == nid

    # Duplicate add -> 409
    r = _client.post("/watchlist", json={"node_id": nid})
    assert r.status_code == 409

    # List
    r = _client.get("/watchlist")
    assert r.status_code == 200
    assert any(i["node_id"] == nid for i in r.json()["items"])

    # Remove
    r = _client.delete(f"/watchlist/{nid}")
    assert r.status_code == 200
    r = _client.delete(f"/watchlist/{nid}")
    assert r.status_code == 404


def test_watchlist_unknown_node():
    r = _client.post("/watchlist", json={"node_id": 999999})
    assert r.status_code == 404


# ---- Source credibility ----------------------------------------------------

def test_source_credibility():
    with SessionLocal() as db:
        sid = _source(db, name="CredSrc", url="https://example.com/cred")
        src = db.get(Source, sid)
        src.last_scanned_at = datetime.now(timezone.utc)
        # 2 good, 1 failed, 1 duplicate -> reliability = (1 - 1/4)*(1 - 1/4)=0.5625
        _article(db, sid, "ok1", status="analyzed", day=0)
        _article(db, sid, "ok2", status="analyzed", day=1)
        _article(db, sid, "bad", status="failed", day=2)
        _article(db, sid, "dup", status="duplicate", day=3)
        db.commit()

    r = _client.get("/sources/credibility")
    assert r.status_code == 200
    row = next(x for x in r.json()["sources"] if x["name"] == "CredSrc")
    c = row["credibility"]
    assert c["articles_total"] == 4
    assert c["failed"] == 1
    assert c["duplicate"] == 1
    assert 50 <= c["score"] <= 60  # ~56.25 * recency
    assert c["grade"] in {"C", "D", "B", "A", "F"}
