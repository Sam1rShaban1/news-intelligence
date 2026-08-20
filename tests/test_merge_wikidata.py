"""Merge must repoint relationships/stories, not cascade-delete them."""

from src.db.models.article import Article
from src.db.models.entity_node import EntityNode
from src.db.models.relationship import Relationship
from src.db.models.source import Source
from src.db.models.story import Story
from src.db.session import SessionLocal
from src.workers.merge_wikidata import run_merge_wikidata


def test_merge_repoints_relationships_and_stories(client):
    with SessionLocal() as db:
        src = Source(name="M", url="https://example.com/m")
        db.add(src)
        db.flush()
        art = Article(
            source_id=src.id,
            url="https://example.com/a",
            url_hash="mh-a",
            status="analyzed",
        )
        db.add(art)
        db.flush()

        canonical = EntityNode(
            canonical_text="Skopje",
            label="LOC",
            wikidata_id="Q1",
            mention_count=5,
            aliases=["Skopje"],
        )
        other = EntityNode(
            canonical_text="Shkup",
            label="LOC",
            wikidata_id="Q1",
            mention_count=3,
            aliases=["Shkup"],
        )
        third = EntityNode(
            canonical_text="North Macedonia",
            label="LOC",
            wikidata_id="Q9",
            mention_count=2,
            aliases=["NMK"],
        )
        db.add_all([canonical, other, third])
        db.flush()

        rel = Relationship(
            subject_node_id=other.id,
            object_node_id=third.id,
            predicate="related",
            article_id=art.id,
        )
        db.add(rel)
        story = Story(title="S", entity_node_ids=[other.id])
        db.add(story)
        db.commit()

        canonical_id, other_id, third_id, rel_id, story_id = (
            canonical.id,
            other.id,
            third.id,
            rel.id,
            story.id,
        )

    assert run_merge_wikidata(dry_run=False) == 1

    with SessionLocal() as db:
        # Merged-away node is gone, relationship survived and was repointed.
        assert db.get(EntityNode, other_id) is None
        rel = db.get(Relationship, rel_id)
        assert rel.subject_node_id == canonical_id
        assert rel.object_node_id == third_id

        # Story now references the canonical node, not the deleted one.
        story = db.get(Story, story_id)
        assert story.entity_node_ids == [canonical_id]

        # Mention count + aliases consolidated onto the canonical node.
        canonical = db.get(EntityNode, canonical_id)
        assert canonical.mention_count == 8
        assert set(canonical.aliases or []) == {"Skopje", "Shkup"}


def test_merge_groups_by_qid_across_labels(client):
    with SessionLocal() as db:
        src = Source(name="M2", url="https://example.com/m2")
        db.add(src)
        db.flush()
        art = Article(
            source_id=src.id,
            url="https://example.com/b",
            url_hash="mh-b",
            status="analyzed",
        )
        db.add(art)
        db.flush()

        a = EntityNode(canonical_text="Skopje", label="PER", wikidata_id="Q1", mention_count=4)
        b = EntityNode(canonical_text="Skopje", label="LOC", wikidata_id="Q1", mention_count=2)
        c = EntityNode(canonical_text="Tirana", label="LOC", wikidata_id="Q2", mention_count=1)
        db.add_all([a, b, c])
        db.flush()

        rel = Relationship(
            subject_node_id=b.id, object_node_id=c.id, predicate="capital", article_id=art.id
        )
        db.add(rel)
        db.commit()
        aid, bid, cid, rel_id = a.id, b.id, c.id, rel.id

    assert run_merge_wikidata(dry_run=False) == 1

    with SessionLocal() as db:
        # b (lower count, different label) merged into a; c untouched.
        assert db.get(EntityNode, bid) is None
        assert db.get(EntityNode, aid) is not None
        assert db.get(EntityNode, cid) is not None
        rel = db.get(Relationship, rel_id)
        assert rel.subject_node_id == aid
        assert rel.object_node_id == cid


def test_merge_dry_run_touches_nothing(client):
    with SessionLocal() as db:
        n1 = EntityNode(canonical_text="A", label="LOC", wikidata_id="QX", mention_count=1)
        n2 = EntityNode(canonical_text="B", label="LOC", wikidata_id="QX", mention_count=1)
        db.add_all([n1, n2])
        db.commit()
        ids = (n1.id, n2.id)

    assert run_merge_wikidata(dry_run=True) == 1

    with SessionLocal() as db:
        assert db.get(EntityNode, ids[0]) is not None
        assert db.get(EntityNode, ids[1]) is not None
