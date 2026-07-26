"""Fetch worker — discovers articles from enabled sources and inserts them."""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from config.settings import settings
from src.collector.dedup import compute_url_hash
from src.collector.fetcher import discover_articles
from src.db.models.article import Article
from src.db.models.source import Source
from src.db.session import SessionLocal
from src.workers.lifecycle import WorkerConfig, is_shutdown_requested

logger = logging.getLogger(__name__)


def run_fetch_cycle(config: WorkerConfig) -> int:
    """
    One fetch cycle: for each enabled source, discover articles, insert new ones.
    Returns the total number of new articles discovered.
    """
    total_new = 0

    with SessionLocal() as session:
        sources = session.execute(
            select(Source).where(Source.enabled.is_(True))
        ).scalars().all()

        for source in sources:
            try:
                count = _fetch_source(session, source, config)
                total_new += count
                # Update scan timestamp on success
                source.last_scanned_at = datetime.now(timezone.utc)
                source.last_error = None
                session.commit()
            except Exception as e:
                source.error_count += 1
                source.last_error = str(e)[:500]
                session.commit()
                logger.warning("Fetch failed for %s: %s", source.name, e)

    return total_new


def _fetch_source(session, source: Source, config: WorkerConfig) -> int:
    """Discover and insert articles for a single source."""
    entries = discover_articles(source)
    if not entries:
        logger.info("No articles found for %s", source.name)
        return 0

    new_count = 0
    for entry in entries:
        if is_shutdown_requested():
            break

        url = entry["url"]
        url_hash = compute_url_hash(url)

        # Check if already exists
        exists = session.execute(
            select(Article.id).where(Article.url_hash == url_hash)
        ).scalar()
        if exists:
            continue

        # Insert new article
        article = Article(
            source_id=source.id,
            url=url,
            url_hash=url_hash,
            title=entry.get("title") or None,
            author=entry.get("author"),
            published_date=entry.get("published_date"),
            summary=entry.get("summary"),
            status="new",
        )
        session.add(article)
        new_count += 1

    if new_count > 0:
        session.commit()
        source.article_count += new_count
        logger.info("Discovered %d new articles for %s", new_count, source.name)

    return new_count


def run_fetch_worker_loop(config: WorkerConfig | None = None) -> None:
    """Main fetch worker loop — runs until shutdown signal."""
    config = config or WorkerConfig()
    logger.info("Fetch worker started, polling every %ds", config.poll_interval)

    while not is_shutdown_requested():
        try:
            count = run_fetch_cycle(config)
            if count:
                logger.info("Fetch cycle complete: %d new articles", count)
        except Exception as e:
            logger.error("Fetch cycle error: %s", e, exc_info=True)

        # Sleep in short increments so we can respond to shutdown
        for _ in range(config.poll_interval):
            if is_shutdown_requested():
                break

    logger.info("Fetch worker stopped")
