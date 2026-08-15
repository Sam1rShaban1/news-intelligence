"""Analyze worker — runs NLP (sentiment + NER) on extracted articles."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, text

from src.db.models.article import Article
from src.db.session import SessionLocal
from src.nlp.analyze import analyze_article, store_results
from src.workers.lifecycle import WorkerConfig, is_shutdown_requested

logger = logging.getLogger(__name__)


def claim_articles(session, batch_size: int, zombie_timeout_minutes: int) -> list[Article]:
    """
    Claim articles ready for sentiment analysis: status='extracted' and not
    currently being processed. After sentiment they move to 'sentiment_done'
    for the separate ner service.
    """
    cutoff = text(f"now() - interval '{zombie_timeout_minutes} minutes'")

    query = (
        select(Article)
        .where(
            Article.status == "extracted",
            Article.started_at.is_(None) | (Article.started_at < cutoff),
            Article.retry_count < 3,
        )
        .order_by(Article.extracted_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    return session.execute(query).scalars().all()


def run_analyze_cycle(config: WorkerConfig) -> int:
    """One analyze cycle: claim articles, run NLP, store results."""
    analyzed_count = 0

    with SessionLocal() as session:
        articles = claim_articles(session, config.batch_size, config.zombie_timeout_minutes)

        for article in articles:
            if is_shutdown_requested():
                break

            # Mark as being processed
            article.started_at = datetime.now(timezone.utc)
            session.commit()

            try:
                results = analyze_article(article)
                store_results(article.id, results)

                article.status = "sentiment_done"
                article.analyzed_at = datetime.now(timezone.utc)
                article.error_message = None
                article.started_at = None
                analyzed_count += 1

                session.commit()
                logger.debug(
                    "Sentiment done: %s (%s %s)",
                    article.title[:40] if article.title else article.url,
                    results["sentiment"]["label"],
                    results["sentiment"]["score"],
                )

            except Exception as e:
                article.retry_count += 1
                article.error_message = str(e)[:500]

                if article.retry_count >= config.max_retries:
                    article.status = "failed"
                    logger.warning("Failed after %d retries: %s", article.retry_count, article.url)
                else:
                    article.status = "extracted"  # reset for retry
                    article.started_at = None

                session.commit()
                logger.debug("Analyze error for %s: %s", article.url, e)

    return analyzed_count


def run_analyze_worker_loop(config: WorkerConfig | None = None) -> None:
    """Main analyze worker loop — runs until shutdown signal."""
    config = config or WorkerConfig()
    logger.info("Analyze worker started, polling every %ds", config.poll_interval)

    while not is_shutdown_requested():
        try:
            count = run_analyze_cycle(config)
            if count:
                logger.info("Analyze cycle: %d articles analyzed", count)
        except Exception as e:
            logger.error("Analyze cycle error: %s", e, exc_info=True)

        for _ in range(config.poll_interval):
            if is_shutdown_requested():
                break

    logger.info("Analyze worker stopped")
