"""API route tests for source management (needs Postgres + migrations)."""

from fastapi.testclient import TestClient

from src.api.main import app
from src.db.models.source import Source
from src.db.session import SessionLocal


def _make(db, **kw) -> int:
    s = Source(
        name=kw.get("name", "Test Source"),
        url=kw.get("url", "https://example.com/feed"),
        rss_url=kw.get("rss_url"),
        enabled=kw.get("enabled", True),
    )
    db.add(s)
    db.commit()
    return s.id


def test_list_empty(client):
    r = client.get("/sources")
    assert r.status_code == 200
    assert r.json()["sources"] == []


def test_create_and_list(client):
    r = client.post(
        "/sources",
        json={"name": "B BC", "url": "https://bbc.example.com", "rss_url": "https://bbc.example.com/rss"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "B BC"
    assert data["enabled"] is True

    r2 = client.get("/sources")
    assert r2.status_code == 200
    assert len(r2.json()["sources"]) == 1


def test_duplicate_url_rejected(client):
    with SessionLocal() as db:
        _make(db, url="https://dup.example.com")
    r = client.post("/sources", json={"name": "X", "url": "https://dup.example.com"})
    assert r.status_code == 400


def test_unsafe_url_rejected(client):
    # Private / loopback addresses must be refused (SSRF guard).
    r = client.post("/sources", json={"name": "X", "url": "http://localhost:8080"})
    assert r.status_code == 400
    r2 = client.post("/sources", json={"name": "X", "url": "ftp://example.com"})
    assert r2.status_code == 400


def test_toggle_and_soft_delete(client):
    with SessionLocal() as db:
        sid = _make(db, url="https://toggle.example.com", enabled=True)

    # disable
    r = client.patch(f"/sources/{sid}", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    # default list excludes soft-deleted
    r = client.delete(f"/sources/{sid}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    listed = client.get("/sources").json()["sources"]
    assert all(s["id"] != sid for s in listed)

    # but visible with include_deleted
    listed_all = client.get("/sources", params={"include_deleted": True}).json()["sources"]
    assert any(s["id"] == sid for s in listed_all)


def test_test_endpoint_uses_discovery(monkeypatch):
    import src.api.routes.sources as sroute

    captured = {}

    def fake_discover(source):
        captured["url"] = source.url
        return [{"url": "https://a.com/1", "title": "T"}]

    monkeypatch.setattr(sroute, "discover_articles", fake_discover)

    with SessionLocal() as db:
        sid = _make(db, url="https://probe.example.com", rss_url="https://probe.example.com/rss")

    with TestClient(app) as c:
        r = c.post(f"/sources/{sid}/test")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["count"] == 1
