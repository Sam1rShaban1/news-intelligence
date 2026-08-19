"""Worker wrapper for periodic Wikidata synonym merging.

After `link_wikidata` resolves entity nodes to Q-ids, nodes that share the same
Q-id (e.g. `shkup` / `skopje`) denote the same real-world entity and should be
collapsed. This runs right after linking in the scheduler so the merge happens
automatically instead of requiring a manual `scripts/merge_by_wikidata.py` run.
"""

import logging

from sqlalchemy import select, text

from src.db.models.entity_node import EntityNode
from src.db.session import SessionLocal

logger = logging.getLogger(__name__)


def run_merge_wikidata(dry_run: bool = False) -> int:
    """Merge canonical nodes that resolve to the same Wikidata Q-id. Returns count.

    Safe to call on a timer: it only touches nodes that already share a Q-id, so once
    the graph is fully merged it becomes a cheap no-op.
    """
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

        for (_qid, _label), members in groups.items():
            if len(members) < 2:
                continue
            members.sort(key=lambda m: m[1], reverse=True)
            canonical, _ = members[0]
            others = [m[0] for m in members[1:]]
            logger.info(
                "merge Wikidata group -> canonical node %d (%d nodes)",
                canonical, len(members),
            )
            for oid in others:
                db.execute(
                    text("UPDATE entities SET node_id = :c WHERE node_id = :o").bindparams(
                        c=canonical, o=oid
                    )
                )
                db.execute(
                    text("UPDATE entity_edges SET node_a_id = :c WHERE node_a_id = :o").bindparams(
                        c=canonical, o=oid
                    )
                )
                db.execute(
                    text("UPDATE entity_edges SET node_b_id = :c WHERE node_b_id = :o").bindparams(
                        c=canonical, o=oid
                    )
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
