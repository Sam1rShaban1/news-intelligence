"""Worker wrapper for periodic Wikidata entity linking."""

import logging

from sqlalchemy import select

from src.db.models.entity_node import EntityNode
from src.db.session import SessionLocal
from src.nlp.wikidata import link_entity

logger = logging.getLogger(__name__)


def run_link_wikidata(limit: int = 200, min_mentions: int = 1) -> int:
    """Link unlinked entity nodes to Wikidata. Returns the number linked.

    Safe to call on a timer: it only touches nodes without a `wikidata_id`, so once
    the graph is fully linked it becomes a cheap no-op. Network failures inside
    `link_entity` are non-fatal.
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
            if not res:
                continue
            node.wikidata_id = res["wikidata_id"]
            node.description = res["description"]
            node.external_ids = res["external_ids"]
            linked += 1
        db.commit()
        logger.info("Wikidata linking: %d/%d nodes linked", linked, len(nodes))
        return linked
