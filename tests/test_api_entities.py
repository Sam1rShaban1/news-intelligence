"""API route tests for the entities endpoints (needs Postgres + migrations)."""

from src.db.models.entity_node import EntityNode
from src.db.session import SessionLocal


def _make_node(db, **kw) -> int:
    node = EntityNode(
        canonical_text=kw.get("canonical_text", "skopje"),
        label=kw.get("label", "LOC"),
        mention_count=kw.get("mention_count", 5),
        wikidata_id=kw.get("wikidata_id"),
        description=kw.get("description"),
        external_ids=kw.get("external_ids"),
    )
    db.add(node)
    db.commit()
    return node.id


def test_entity_node_detail_404(client):
    r = client.get("/entities/nodes/999999")
    assert r.status_code == 404


def test_entity_node_detail_with_wikidata(client):
    with SessionLocal() as db:
        nid = _make_node(
            db,
            wikidata_id="Q2004",
            description="Capital of North Macedonia",
            external_ids={"wikipedia": "Skopje"},
        )
    try:
        r = client.get(f"/entities/nodes/{nid}")
        assert r.status_code == 200
        data = r.json()
        assert data["wikidata_id"] == "Q2004"
        assert data["wikidata_url"] == "https://www.wikidata.org/wiki/Q2004"
        assert data["description"] == "Capital of North Macedonia"
        assert data["external_ids"] == {"wikipedia": "Skopje"}
    finally:
        with SessionLocal() as db:
            db.query(EntityNode).filter(EntityNode.id == nid).delete()
            db.commit()


def test_entity_node_detail_without_wikidata(client):
    with SessionLocal() as db:
        nid = _make_node(db, wikidata_id=None, description=None)
    try:
        r = client.get(f"/entities/nodes/{nid}")
        assert r.status_code == 200
        data = r.json()
        assert data["wikidata_id"] is None
        assert data["wikidata_url"] is None
    finally:
        with SessionLocal() as db:
            db.query(EntityNode).filter(EntityNode.id == nid).delete()
            db.commit()


def test_entity_nodes_list_filters_and_paginates(client):
    with SessionLocal() as db:
        a = _make_node(db, canonical_text="tirana", label="LOC", mention_count=10)
        b = _make_node(db, canonical_text="rama", label="PER", mention_count=3)
    try:
        r = client.get("/entities/nodes", params={"limit": 5})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 2

        r_loc = client.get("/entities/nodes", params={"label": "LOC"})
        ids = {n["id"] for n in r_loc.json()["nodes"]}
        assert a in ids and b not in ids

        r_q = client.get("/entities/nodes", params={"q": "tir"})
        texts = {n["text"] for n in r_q.json()["nodes"]}
        assert "tirana" in texts
    finally:
        with SessionLocal() as db:
            db.query(EntityNode).filter(EntityNode.id.in_([a, b])).delete()
            db.commit()


def test_node_articles_empty(client):
    with SessionLocal() as db:
        nid = _make_node(db)
    try:
        r = client.get(f"/entities/{nid}/articles", params={"limit": 10})
        assert r.status_code == 200
        assert r.json()["articles"] == []
    finally:
        with SessionLocal() as db:
            db.query(EntityNode).filter(EntityNode.id == nid).delete()
            db.commit()
