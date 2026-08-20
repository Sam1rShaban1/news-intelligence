"""Embeddings worker — computes text embeddings for analyzed articles (VPS tier).

Runs as its own service (`python -m src.workers.embeddings_service`). For each analyzed
article without an embedding it computes one (real model on VPS, deterministic fallback
otherwise) and stores it, enabling semantic / nearest-neighbour search.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from config.settings import settings
from src.db.models.article import Article
from src.db.session import SessionLocal
from src.nlp.embeddings import get_embedder
from src.workers.lifecycle import WorkerConfig, install_signal_handlers, is_shutdown_requested

logger = logging.getLogger(__name__)


def run_embeddings_cycle(config: WorkerConfig, batch_size: int = 32) -> int:
    """One pass: embed analyzed articles that have no embedding yet. Returns count."""
    embedder = get_embedder()
    now = datetime.now(timezone.utc)
    done = 0
    with SessionLocal() as db:
        articles = db.execute(
            select(Article)
            .where(Article.status == "analyzed", Article.embedding.is_(None))
            .limit(batch_size)
        ).scalars().all()
        if not articles:
            return 0
        for a in articles:
            text = " ".join(
                part for part in (a.title, a.summary, a.content) if part
            )
            vec = embedder.embed([text or a.url or ""])[0]
            a.embedding = vec
            a.embedded_at = now
            done += 1
        db.commit()
    return done


def run_embeddings_worker_loop(config: WorkerConfig | None = None) -> None:
    if not settings.feature_embeddings:
        logger.warning("FEATURE_EMBEDDINGS is disabled — embeddings worker will not run. Exiting.")
        return
    config = config or WorkerConfig()
    logger.info("Embeddings worker started, embedding every %ds", config.poll_interval)
    while not is_shutdown_requested():
        try:
            n = run_embeddings_cycle(config)
            if n:
                logger.info("Embeddings cycle: %d article(s) embedded", n)
        except Exception as e:
            logger.error("Embeddings cycle error: %s", e, exc_info=True)
        for _ in range(config.poll_interval):
            if is_shutdown_requested():
                break
    logger.info("Embeddings worker stopped")


def main() -> None:
    install_signal_handlers()
    logger.info("Embeddings worker starting...")
    run_embeddings_worker_loop()


if __name__ == "__main__":
    main()
