"""Worker wrapper for periodic Wikidata entity linking."""

import logging
import os
import time

from sqlalchemy import select

from src.db.models.entity_node import EntityNode
from src.db.session import SessionLocal
from src.nlp.wikidata import link_entity

logger = logging.getLogger(__name__)

# Politeness delay between Wikidata API calls (seconds).
LINK_DELAY = float(os.environ.get("WIKIDATA_DELAY", "0.15"))


def run_link_wikidata(limit: int = 200, min_mentions: int = 3) -> int:
    """Link unlinked entity nodes to Wikidata. Returns the number linked.

    Safe to call on a timer: it only touches nodes without a `wikidata_id` (and only
    those seen often enough to clear `min_mentions`), so once the graph is fully linked
    it becomes a cheap no-op. Network failures / rate limiting inside `link_entity` are
    non-fatal; a small delay between calls keeps us polite to the public API.
    """
    with SessionLocal() as db:
        nodes = (
            db.execute(
                select(EntityNode)
                .where(EntityNode.wikidata_id.is_(None))
                .where(EntityNode.mention_count >= min_mentions)
                .order_by(EntityNode.mention_count.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        linked = 0
        for node in nodes:
            res = link_entity(node.canonical_text, node.label)
            if res:
                node.wikidata_id = res["wikidata_id"]
                node.description = res["description"]
                node.external_ids = res["external_ids"]
                linked += 1
            time.sleep(LINK_DELAY)
        db.commit()
        logger.info("Wikidata linking: %d/%d nodes linked", linked, len(nodes))
        return linked
