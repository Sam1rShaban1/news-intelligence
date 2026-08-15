"""NER service — runs GLiNER2 ONNX NER + normalization + co-occurrence graph.

This is a SEPARATE container/service from the main worker so the heavy ONNX
model never blocks fetch/extract/sentiment. It claims `sentiment_done` articles,
extracts entities, builds the knowledge graph, and marks them `analyzed`.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, text

from src.db.models.article import Article
from src.db.session import SessionLocal
from src.nlp.graph import build_article_graph
from src.nlp.ner import extract_entities
from src.nlp.relations import build_relationships
from src.workers.lifecycle import WorkerConfig, install_signal_handlers, is_shutdown_requested

logger = logging.getLogger(__name__)


def claim_articles(session, batch_size: int, zombie_timeout_minutes: int) -> list[Article]:
    """Claim articles whose sentiment is done and are awaiting NER."""
    cutoff = text(f"now() - interval '{zombie_timeout_minutes} minutes'")

    query = (
        select(Article)
        .where(
            Article.status == "sentiment_done",
            Article.started_at.is_(None) | (Article.started_at < cutoff),
            Article.retry_count < 3,
        )
        .order_by(Article.analyzed_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    return session.execute(query).scalars().all()


def run_ner_cycle(config: WorkerConfig) -> int:
    """One NER cycle: claim articles, extract entities, build graph."""
    processed = 0

    with SessionLocal() as session:
        articles = claim_articles(session, config.batch_size, config.zombie_timeout_minutes)

        for article in articles:
            if is_shutdown_requested():
                break

            article.started_at = datetime.now(timezone.utc)
            session.commit()

            try:
                text = article.content or article.summary or article.title or ""
                raw_entities = extract_entities(text)
                build_article_graph(session, article.id, raw_entities)
                triples = build_relationships(session, article.id, raw_entities, text)

                article.status = "analyzed"
                article.analyzed_at = datetime.now(timezone.utc)
                article.error_message = None
                article.started_at = None
                processed += 1

                session.commit()
                logger.debug(
                    "NER done: %s (%d entities, %d triples)",
                    article.title[:40] if article.title else article.url,
                    len(raw_entities),
                    triples,
                )

            except Exception as e:
                article.retry_count += 1
                article.error_message = str(e)[:500]

                if article.retry_count >= config.max_retries:
                    article.status = "failed"
                    logger.warning("NER failed after %d retries: %s", article.retry_count, article.url)
                else:
                    article.status = "sentiment_done"  # reset for retry
                    article.started_at = None

                session.commit()
                logger.debug("NER error for %s: %s", article.url, e)

    return processed


def run_ner_worker_loop(config: WorkerConfig | None = None) -> None:
    """Main NER worker loop — runs until shutdown signal."""
    config = config or WorkerConfig()
    logger.info("NER service started, polling every %ds", config.poll_interval)

    while not is_shutdown_requested():
        try:
            count = run_ner_cycle(config)
            if count:
                logger.info("NER cycle: %d articles analyzed", count)
        except Exception as e:
            logger.error("NER cycle error: %s", e, exc_info=True)

        for _ in range(config.poll_interval):
            if is_shutdown_requested():
                break

    logger.info("NER service stopped")


def main() -> None:
    install_signal_handlers()
    logger.info("NER service starting...")
    config = WorkerConfig()
    run_ner_worker_loop(config)


if __name__ == "__main__":
    main()
