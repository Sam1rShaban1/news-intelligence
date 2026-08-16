"""Fetch worker — discovers articles from enabled sources and inserts them."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# Network discovery is the slow part of a fetch cycle (per-source HTTP). Run it
# concurrently; DB writes stay sequential in the main thread (sessions aren't
# thread-safe).
FETCH_CONCURRENCY = 8


def run_fetch_cycle(config: WorkerConfig) -> int:
    """
    One fetch cycle: discover articles from all enabled sources (concurrently),
    then insert new ones. Returns the total number of new articles discovered.
    """
    total_new = 0

    with SessionLocal() as session:
        sources = session.execute(
            select(Source).where(Source.enabled.is_(True))
        ).scalars().all()
        if not sources:
            return 0

        # Concurrent network discovery; results keyed by source id.
        results: dict[int, object] = {}
        with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as ex:
            futures = {ex.submit(discover_articles, s): s for s in sources}
            for fut in as_completed(futures):
                s = futures[fut]
                try:
                    results[s.id] = fut.result()
                except Exception as e:  # discovery error -> handled below
                    results[s.id] = e

        # Sequential DB processing (thread-safe single session).
        for source in sources:
            try:
                entries = results.get(source.id)
                if isinstance(entries, Exception):
                    raise entries
                count = _process_source(session, source, entries or [])
                total_new += count
                source.last_scanned_at = datetime.now(timezone.utc)
                source.last_error = None
            except Exception as e:
                source.error_count += 1
                source.last_error = str(e)[:500]
                logger.warning("Fetch failed for %s: %s", source.name, e)
            finally:
                session.commit()

    return total_new


def _process_source(session, source: Source, entries: list[dict]) -> int:
    """Insert new articles for a single source. Returns count of new articles."""
    if not entries:
        logger.info("No articles found for %s", source.name)
        return 0

    new_count = 0
    for entry in entries:
        if is_shutdown_requested():
            break

        url = entry["url"]
        url_hash = compute_url_hash(url)

        exists = session.execute(
            select(Article.id).where(Article.url_hash == url_hash)
        ).scalar()
        if exists:
            continue

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
