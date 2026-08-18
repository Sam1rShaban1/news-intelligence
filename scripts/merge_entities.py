#!/usr/bin/env python
"""Universal, data-driven entity de-duplication (NO hardcoded alias lists).

Collapses EntityNodes that are surface-form variants of the same real-world entity
via string similarity on the normalized canonical text
(src.nlp.normalize.entity_similarity) — inflectional / near-spelling variants such
as shkup / shkupi / shkupit, macedonia / maqedonia, ohrid / ohrida.

NOTE: co-occurrence-based merging was removed. In news, entities that appear in the
same article are normally *different* entities in the same story, so merging by
co-occurrence produced false merges (e.g. Saudi Arabia -> Dublin). Canonicalization
of cross-language synonyms that never share a surface form is instead left to the
per-extraction fuzzy resolution in src/nlp/graph.py.

All candidate merges are collected into a union-find, then each cluster is collapsed
onto its highest-mention-count canonical node. Every merge is logged.

Set DRY_RUN=1 to only print the planned merges without touching the database:
    DRY_RUN=1 docker compose run --rm worker scripts/merge_entities.py
"""

import logging
import os
import sys

from sqlalchemy import select, text

from src.db.models.entity_edge import EntityEdge
from src.db.models.entity_node import EntityNode
from src.db.session import SessionLocal
from src.nlp.normalize import entity_similarity

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Minimum normalized-text similarity for two same-label nodes to be treated as the
# same entity. 0.85 is conservative; 0.80 also catches near-spelling cross-language
# pairs like kosova/kosovo (0.833) while still excluding shkup/skopje (0.55) and
# pristina/prishtine (0.79). Override with SIMILARITY_THRESHOLD if needed.
SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.8"))
DRY_RUN = os.environ.get("DRY_RUN") == "1"


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _load_nodes(session):
    nodes = {}
    for nid, label, canonical, mc in session.execute(
        select(
            EntityNode.id, EntityNode.label, EntityNode.canonical_text, EntityNode.mention_count
        )
    ).all():
        nodes[nid] = {"label": label, "canonical": canonical, "mentions": mc or 0}
    return nodes


def _find_similarity_merges(nodes):
    """Yield (a_id, b_id) pairs whose normalized text is near-identical."""
    by_label = {}
    for nid, info in nodes.items():
        by_label.setdefault(info["label"], []).append(nid)

    for label, ids in by_label.items():
        for i in range(len(ids)):
            a = ids[i]
            ca = nodes[a]["canonical"]
            la = len(ca)
            for j in range(i + 1, len(ids)):
                b = ids[j]
                cb = nodes[b]["canonical"]
                if abs(len(cb) - la) > 2 or cb[:1] != ca[:1]:
                    continue
                score = entity_similarity(ca, cb)
                if score >= SIMILARITY_THRESHOLD:
                    yield a, b, round(score, 3)


def _repoint_entities(session, variant_id, canonical_id):
    session.execute(
        text("UPDATE entities SET node_id = :c WHERE node_id = :v").bindparams(
            c=canonical_id, v=variant_id
        )
    )


def _repoint_edges(session, variant_id, canonical_id):
    for a_id, b_id, w in session.execute(
        select(EntityEdge.node_a_id, EntityEdge.node_b_id, EntityEdge.weight).where(
            (EntityEdge.node_a_id == variant_id) | (EntityEdge.node_b_id == variant_id)
        )
    ).all():
        a = canonical_id if a_id == variant_id else a_id
        b = canonical_id if b_id == variant_id else b_id
        if a == b:
            session.execute(
                text("DELETE FROM entity_edges WHERE node_a_id = :a AND node_b_id = :b").bindparams(
                    a=a, b=b
                )
            )
            continue
        if a > b:
            a, b = b, a
        session.execute(
            text(
                "INSERT INTO entity_edges (node_a_id, node_b_id, weight) "
                "VALUES (:a, :b, :w) "
                "ON CONFLICT (node_a_id, node_b_id) DO UPDATE SET weight = entity_edges.weight + :w"
            ).bindparams(a=a, b=b, w=w)
        )
        session.execute(
            text("DELETE FROM entity_edges WHERE node_a_id = :a AND node_b_id = :b").bindparams(
                a=a_id, b=b_id
            )
        )


def _repoint_stories(session, variant_id, canonical_id):
    session.execute(
        text(
            "UPDATE stories SET entity_node_ids = ("
            "  SELECT ARRAY_AGG(DISTINCT x ORDER BY x) FROM unnest(ARRAY("
            "    SELECT CASE WHEN x = :v THEN :c ELSE x END FROM unnest(entity_node_ids) AS t(x)"
            "  )) AS u(x) WHERE x IS NOT NULL"
            ") WHERE :v = ANY(entity_node_ids)"
        ).bindparams(v=variant_id, c=canonical_id)
    )


def _merge_cluster(session, ids, nodes):
    """Collapse all `ids` into the highest-mention-count node; delete the rest."""
    canonical_id = max(ids, key=lambda nid: (nodes[nid]["mentions"], -len(nodes[nid]["canonical"])))
    variants = [nid for nid in ids if nid != canonical_id]
    if not variants:
        return

    c_node = session.get(EntityNode, canonical_id)
    for v_id in variants:
        v_node = session.get(EntityNode, v_id)
        _repoint_entities(session, v_id, canonical_id)
        _repoint_edges(session, v_id, canonical_id)
        _repoint_stories(session, v_id, canonical_id)
        c_node.mention_count = (c_node.mention_count or 0) + (v_node.mention_count or 0)
        if v_node.aliases:
            existing = list(c_node.aliases or [])
            for al in v_node.aliases:
                if al not in existing:
                    existing.append(al)
            c_node.aliases = existing
        session.delete(v_node)
        logger.info(
            "MERGE %s (id=%s, mc=%s) -> %s (id=%s, mc=%s)",
            nodes[v_id]["canonical"], v_id, v_node.mention_count,
            nodes[canonical_id]["canonical"], canonical_id, c_node.mention_count,
        )


def main() -> int:
    with SessionLocal() as session:
        nodes = _load_nodes(session)
        logger.info("Loaded %d entity nodes", len(nodes))

        uf = UnionFind()
        sim_count = 0
        for a, b, score in _find_similarity_merges(nodes):
            uf.union(a, b)
            sim_count += 1
        logger.info("Candidate merges: %d similarity", sim_count)

        clusters: dict = {}
        for nid in nodes:
            clusters.setdefault(uf.find(nid), []).append(nid)
        mergeable = [ids for ids in clusters.values() if len(ids) > 1]
        logger.info("Resolved into %d merge clusters", len(mergeable))

        if DRY_RUN:
            for ids in mergeable:
                canonical_id = max(
                    ids, key=lambda nid: (nodes[nid]["mentions"], -len(nodes[nid]["canonical"]))
                )
                members = ", ".join(
                    f"{nodes[n]['canonical']}({nodes[n]['mentions']})"
                    for n in ids
                    if n != canonical_id
                )
                logger.info("WOULD MERGE [%s] -> %s", members, nodes[canonical_id]["canonical"])
            logger.info("DRY_RUN: no changes made.")
            return 0

        for ids in mergeable:
            _merge_cluster(session, ids, nodes)
        session.commit()
        logger.info("Done. Merged %d clusters.", len(mergeable))
    return 0


if __name__ == "__main__":
    sys.exit(main())
