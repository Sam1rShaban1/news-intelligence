"""Worker wrapper for periodic Wikidata synonym merging.

After `link_wikidata` resolves entity nodes to Q-ids, nodes that share the same
Q-id (e.g. `shkup` / `skopje`) denote the same real-world entity and should be
collapsed. This runs right after linking in the scheduler so the merge happens
automatically instead of requiring a manual `scripts/merge_by_wikidata.py` run.

Merging must NOT drop data: relationships and stories that reference a merged-away
node are repointed to the canonical node before the redundant node is deleted, so
the knowledge graph keeps every edge (the FK is `ON DELETE CASCADE`, so deleting a
node would otherwise silently destroy every relationship that touched it).
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
        groups: dict[str, list[tuple[int, int]]] = {}
        for nid, qid, label, mc in rows:
            groups.setdefault(qid, []).append((nid, mc or 0))

        for _qid, members in groups.items():
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
                # Repoint co-occurrence edges.
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
                # Repoint relationship triples (the data-loss bug: FK is CASCADE).
                db.execute(
                    text(
                        "UPDATE relationships SET subject_node_id = :c WHERE subject_node_id = :o"
                    ).bindparams(c=canonical, o=oid)
                )
                db.execute(
                    text(
                        "UPDATE relationships SET object_node_id = :c WHERE object_node_id = :o"
                    ).bindparams(c=canonical, o=oid)
                )
                # Repoint stories that listed the merged-away node.
                db.execute(
                    text(
                        "UPDATE stories "
                        "SET entity_node_ids = ("
                        "  SELECT coalesce(array_agg(DISTINCT v ORDER BY v), ARRAY[]::integer[]) "
                        "  FROM unnest(coalesce(entity_node_ids, ARRAY[]::integer[])) v "
                        "  WHERE v <> :o"
                        ") || CASE WHEN :c = ANY(coalesce(entity_node_ids, ARRAY[]::integer[])) "
                        "          THEN ARRAY[]::integer[] ELSE ARRAY[:c]::integer[] END "
                        "WHERE :o = ANY(coalesce(entity_node_ids, ARRAY[]::integer[]))"
                    ).bindparams(c=canonical, o=oid)
                )
                # Consolidate mention count + aliases onto the canonical node
                # (no data loss: counts add up, alias lists union).
                other_node = db.get(EntityNode, oid)
                canonical_node = db.get(EntityNode, canonical)
                if other_node is not None and canonical_node is not None:
                    canonical_node.mention_count = (canonical_node.mention_count or 0) + (
                        other_node.mention_count or 0
                    )
                    merged_aliases = set(canonical_node.aliases or []) | set(
                        other_node.aliases or []
                    )
                    canonical_node.aliases = sorted(merged_aliases)

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

            # Same hygiene for relationship triples: drop self-loops and dupes.
            db.execute(text("DELETE FROM relationships WHERE subject_node_id = object_node_id"))
            db.execute(
                text(
                    "DELETE FROM relationships a "
                    "WHERE EXISTS (SELECT 1 FROM relationships b "
                    "WHERE b.subject_node_id = a.subject_node_id "
                    "AND b.object_node_id = a.object_node_id "
                    "AND b.predicate = a.predicate "
                    "AND b.article_id = a.article_id "
                    "AND b.id > a.id)"
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
