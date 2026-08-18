#!/usr/env python
"""Merge canonical entity nodes that resolve to the same Wikidata entity.

Cross-lingual synonyms (e.g. `shkup` / `skopje`) never share a surface form, so
the fuzzy `merge_entities.py` cannot merge them. But once both nodes are linked
to the same Wikidata Q-id (via `scripts/link_wikidata.py`), they clearly denote
the same real-world entity and should be collapsed into one node.

For each (wikidata_id, label) group with more than one node:
  - the highest-mention node becomes canonical,
  - raw `entity` mentions and co-occurrence `entity_edges` are reassigned,
  - self-loops and reversed/duplicate edges are removed.

Run with DRY_RUN=1 to preview. Requires Postgres (uses LEAST/GREATEST).
"""

import logging
import os

from sqlalchemy import select, text

from src.db.models.entity_node import EntityNode
from src.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DRY_RUN = os.environ.get("DRY_RUN") == "1"


def merge_by_wikidata(dry_run: bool = DRY_RUN) -> int:
    merges = 0
    with SessionLocal() as db:
        rows = (
            db.execute(
                select(
                    EntityNode.id,
                    EntityNode.wikidata_id,
                    EntityNode.label,
                    EntityNode.mention_count,
                ).where(EntityNode.wikidata_id.isnot(None))
            )
            .tuples()
            .all()
        )
        groups: dict[tuple[str, str], list[tuple[int, int]]] = {}
        for nid, qid, label, mc in rows:
            groups.setdefault((qid, label), []).append((nid, mc or 0))

        for (qid, label), members in groups.items():
            if len(members) < 2:
                continue
            members.sort(key=lambda m: m[1], reverse=True)
            canonical, _ = members[0]
            others = [m[0] for m in members[1:]]
            logger.info(
                "merge %s/%s -> canonical node %d (from %d nodes)",
                label, qid, canonical, len(members),
            )
            for oid in others:
                db.execute(
                    text("UPDATE entities SET node_id = :c WHERE node_id = :o")
                    .bindparams(c=canonical, o=oid)
                )
                db.execute(
                    text("UPDATE entity_edges SET node_a_id = :c WHERE node_a_id = :o")
                    .bindparams(c=canonical, o=oid)
                )
                db.execute(
                    text("UPDATE entity_edges SET node_b_id = :c WHERE node_b_id = :o")
                    .bindparams(c=canonical, o=oid)
                )
            # Remove self-loops, normalise ordering (node_a_id < node_b_id),
            # and collapse duplicate edges keeping the max weight.
            db.execute(text("DELETE FROM entity_edges WHERE node_a_id = node_b_id"))
            db.execute(
                text(
                    "UPDATE entity_edges "
                    "SET node_a_id = LEAST(node_a_id, node_b_id), "
                    "node_b_id = GREATEST(node_a_id, node_b_id) "
                    "WHERE node_a_id > node_b_id"
                )
            )
            db.execute(
                text(
                    "DELETE FROM entity_edges a "
                    "WHERE EXISTS (SELECT 1 FROM entity_edges b "
                    "WHERE b.node_a_id = a.node_a_id AND b.node_b_id = a.node_b_id "
                    "AND (b.weight > a.weight OR (b.weight = a.weight AND b.id > a.id)))"
                )
            )
            db.execute(
                text("DELETE FROM entity_nodes WHERE id = ANY(:others)").bindparams(others=others)
            )
            merges += 1

        if not dry_run:
            db.commit()
        logger.info("Wikidata merge: %d groups merged (dry_run=%s)", merges, dry_run)
        return merges


if __name__ == "__main__":
    merge_by_wikidata()
