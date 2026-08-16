"""Co-occurrence graph building from extracted entities.

For each analyzed article we:
  1. Resolve each raw mention to a canonical EntityNode (creating/updating as needed).
  2. Record the per-article mention (Entity row with node_id + normalized_text).
  3. For every pair of distinct nodes in the article, increment the undirected
     co-occurrence edge weight by 1.
"""

import logging
from datetime import datetime, timezone
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.db.models.entity import Entity
from src.db.models.entity_edge import EntityEdge
from src.db.models.entity_node import EntityNode
from src.nlp.normalize import normalize_entity

logger = logging.getLogger(__name__)


def get_or_create_node(
    session, canonical: str, label: str, raw_alias: str | None, now: datetime
) -> EntityNode:
    """Find the canonical node (exact, normalized match), creating it if missing.

    De-duplication of surface-form variants (e.g. shkup / shkupi, transliterated
    Cyrillic, digit/diacritic noise) is handled by `normalize_entity`, so this only
    matches on the already-normalized canonical text. Any further merging of
    residual near-duplicates is done explicitly and reviewably via
    scripts/merge_entities.py (similarity-only, DRY_RUN first) — never implicitly
    during ingestion, to avoid false merges.
    """
    node = session.execute(
        select(EntityNode).where(
            EntityNode.canonical_text == canonical, EntityNode.label == label
        )
    ).scalar()

    if node is None:
        node = EntityNode(
            canonical_text=canonical,
            label=label,
            aliases=[raw_alias] if raw_alias else [],
            mention_count=0,
            first_seen=now,
            last_seen=now,
        )
        session.add(node)
        session.flush()
        return node

    node.last_seen = now
    if raw_alias and (node.aliases is None or raw_alias not in node.aliases):
        existing = list(node.aliases or [])
        existing.append(raw_alias)
        node.aliases = existing
    return node


def increment_cooccurrence(session, node_ids: list[int]) -> None:
    """Increment undirected co-occurrence edges for all pairs in `node_ids`."""
    unique = sorted(set(node_ids))
    for a, b in combinations(unique, 2):
        stmt = pg_insert(EntityEdge).values(node_a_id=a, node_b_id=b, weight=1)
        stmt = stmt.on_conflict_do_update(
            index_elements=["node_a_id", "node_b_id"],
            set_={"weight": EntityEdge.weight + 1},
        )
        session.execute(stmt)


def build_article_graph(session, article_id: int, raw_entities: list[dict]) -> int:
    """
    Resolve `raw_entities` (list of {text, label, start, end, confidence})
    into canonical nodes + mentions, then build co-occurrence edges.

    Existing mentions for the article are cleared first so re-runs are idempotent
    at the mention level (edge weights may still grow on a failure-retry).

    Returns the number of distinct nodes linked to this article.
    """
    now = datetime.now(timezone.utc)

    # Clean slate for this article's mentions (idempotent re-run).
    session.execute(
        Entity.__table__.delete().where(Entity.article_id == article_id)
    )

    # Dedupe by (text, label) within the article to respect the unique constraint.
    seen: set[tuple[str, str]] = set()
    node_ids: list[int] = []

    for ent in raw_entities:
        text = (ent.get("text") or "").strip()
        label = (ent.get("label") or "MISC").upper()
        if not text:
            continue
        key = (text, label)
        if key in seen:
            continue
        seen.add(key)

        canonical = normalize_entity(text, label)
        if not canonical:
            continue

        node = get_or_create_node(session, canonical, label, raw_alias=text, now=now)
        node.mention_count += 1
        session.flush()
        node_ids.append(node.id)

        session.add(
            Entity(
                article_id=article_id,
                text=text,
                label=label,
                start_pos=ent.get("start"),
                end_pos=ent.get("end"),
                confidence=ent.get("confidence"),
                normalized_text=canonical,
                node_id=node.id,
            )
        )

    session.flush()
    if len(node_ids) >= 2:
        increment_cooccurrence(session, node_ids)
    session.flush()

    return len(node_ids)
