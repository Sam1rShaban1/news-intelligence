#!/usr/bin/env python
"""Link canonical entity nodes to Wikidata.

Resolves `entity_nodes` with no `wikidata_id` to a Wikidata Q-id (and stores a
short description + external ids). This powers stable, language-independent
entity identifiers and cross-lingual synonym merging.

Run manually:
    docker compose run --rm worker scripts/link_wikidata.py
    DRY_RUN=1 docker compose run --rm worker scripts/link_wikidata.py

It is also invoked periodically by the worker scheduler.
"""

import logging
import os
import time

from sqlalchemy import select

from src.db.models.entity_node import EntityNode
from src.db.session import SessionLocal
from src.nlp.wikidata import link_entity

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

LINK_BATCH = int(os.environ.get("WIKIDATA_BATCH", "200"))
MIN_MENTIONS = int(os.environ.get("WIKIDATA_MIN_MENTIONS", "1"))
LINK_DELAY = float(os.environ.get("WIKIDATA_DELAY", "0.15"))
DRY_RUN = os.environ.get("DRY_RUN") == "1"


def link_pending(
    limit: int = LINK_BATCH, min_mentions: int = MIN_MENTIONS, dry_run: bool = DRY_RUN
) -> int:
    """Link up to `limit` unlinked nodes (above `min_mentions`). Returns count linked."""
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
            logger.info(
                "linked %s/%s -> %s", node.label, node.canonical_text, res["wikidata_id"]
            )
            time.sleep(LINK_DELAY)
        if not dry_run:
            db.commit()
        logger.info(
            "Wikidata linking: %d/%d nodes linked (dry_run=%s)",
            linked, len(nodes), dry_run,
        )
        return linked


if __name__ == "__main__":
    link_pending()
