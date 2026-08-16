#!/usr/bin/env python
"""Recompute search_vector for all articles using transliterated Latin text.

Run once after deploy to backfill existing rows whose search_vector was
populated by the old PL/pgSQL trigger (raw Cyrillic). Uses normalize_text
(Cyrillic->Latin, diacritic fold) so MK/SQ are searchable via Latin queries.

Usage:
    docker compose run --rm worker scripts/backfill_search_vector.py
"""

import logging
import sys

from sqlalchemy import func, select, update

from src.db.models.article import Article
from src.db.session import SessionLocal
from src.nlp.normalize import normalize_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH = 200


def main() -> int:
    count = 0
    with SessionLocal() as session:
        while True:
            batch = session.execute(
                select(Article.id, Article.title, Article.content)
                .where(Article.status.in_(["extracted", "sentiment_done", "analyzed"]))
                .order_by(Article.id)
                .limit(BATCH)
            ).all()
            if not batch:
                break

            for art_id, title, content in batch:
                raw = f"{title or ''} {content or ''}"
                session.execute(
                    update(Article)
                    .where(Article.id == art_id)
                    .values(search_vector=func.to_tsvector("simple", normalize_text(raw)))
                )
                count += 1

            session.commit()
            logger.info("Backfilled %d articles", count)

    logger.info("Done. Recomputed search_vector for %d articles.", count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
