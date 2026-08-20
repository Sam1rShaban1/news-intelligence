"""Search must rank cross-script (Macedonian Cyrillic <-> Latin) queries."""

from fastapi.testclient import TestClient

from src.api.main import app
from src.db.models.article import Article
from src.db.models.source import Source
from src.db.session import SessionLocal
from src.nlp.normalize import normalize_text

_client = TestClient(app)


def test_cross_script_search_ranks_matches(client):
    with SessionLocal() as db:
        src = Source(name="RS", url="https://example.com/rs")
        db.add(src)
        db.flush()
        art = Article(
            source_id=src.id,
            url="https://example.com/x",
            url_hash="sh-x",
            title="Скопје е главен град",
            status="analyzed",
            language="mk",
        )
        art.search_vector = func_to_tsvector(
            "Скопје е главен град на Северна Македонија"
        )
        db.add(art)
        db.commit()
        aid = art.id

    # Latin query must match the Cyrillic article and rank it above zero.
    r = _client.get("/search", params={"q": "skopje"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert aid in [x["id"] for x in results]
    hit = next(x for x in results if x["id"] == aid)
    assert hit["rank"] is not None and hit["rank"] > 0

    # Cyrillic query must also match (normalized the same way).
    r2 = _client.get("/search", params={"q": "Скопје"})
    assert r2.status_code == 200
    assert aid in [x["id"] for x in r2.json()["results"]]


def func_to_tsvector(text: str):
    from sqlalchemy import func

    return func.to_tsvector("simple", normalize_text(text))
