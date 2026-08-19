#!/usr/bin/env python
"""Recompute `language` for all extracted articles.

Run once after deploying improved language detection to fix rows that were
mislabeled (e.g. Turkish/Macedonian classified as English by the old detector,
or HTML-laden content confusing the classifier). Language is only set at extract
time, so already-extracted articles keep their original label until re-detected;
the NLP analyze stage also re-detects on every (re-)analysis, but this script
backfills the existing backlog in one pass.

Usage:
    docker compose run --rm worker scripts/redetect_language.py
"""

import logging
import sys

from sqlalchemy import select, update

from src.db.models.article import Article
from src.db.session import SessionLocal
from src.nlp.language import detect_language

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH = 200


def main() -> int:
    changed = 0
    last_id = 0
    with SessionLocal() as session:
        while True:
            batch = session.execute(
                select(Article.id, Article.title, Article.content, Article.language)
                .where(Article.id > last_id)
                .order_by(Article.id)
                .limit(BATCH)
            ).all()
            if not batch:
                break

            for art_id, title, content, old_lang in batch:
                new_lang = detect_language(title or content)
                if new_lang != old_lang:
                    session.execute(
                        update(Article).where(Article.id == art_id).values(language=new_lang)
                    )
                    changed += 1

            last_id = batch[-1].id
            session.commit()
            logger.info("Scanned up to id=%d (%d changed so far)", last_id, changed)

    logger.info("Done. Updated language for %d articles.", changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
