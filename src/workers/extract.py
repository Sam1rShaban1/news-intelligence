"""Extract worker — fetches article content from discovered URLs."""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select, text

from src.collector.dedup import compute_content_hash
from src.collector.extractor import extract_article
from src.db.models.article import Article
from src.db.session import SessionLocal
from src.nlp.language import detect_language
from src.nlp.normalize import normalize_text
from src.nlp.summarize import extractive_summary
from src.workers.lifecycle import WorkerConfig, is_shutdown_requested

logger = logging.getLogger(__name__)


def find_duplicate(db, article_id: int, content_hash: str) -> int | None:
    """Return the id of an already-processed article with the same body, if any."""
    row = db.execute(
        select(Article.id).where(
            Article.content_hash == content_hash,
            Article.id != article_id,
            Article.status.in_(["extracted", "sentiment_done", "analyzed"]),
        )
    ).first()
    return row[0] if row else None


def claim_articles(session, batch_size: int, zombie_timeout_minutes: int) -> list[Article]:
    """
    Claim articles ready for extraction using SELECT ... FOR UPDATE SKIP LOCKED.
    Returns claimed articles.
    """
    cutoff = text("now() - INTERVAL '1 minute' * :minutes").bindparams(
        minutes=zombie_timeout_minutes
    )

    # Claim new articles or zombies (including our own in-progress state, so a
    # worker killed mid-extract is reclaimed after the zombie timeout).
    query = (
        select(Article)
        .where(
            Article.status.in_(["fetched", "new", "extracting"]),
            (Article.started_at.is_(None)) | (Article.started_at < cutoff),
            Article.retry_count < 3,
        )
        .order_by(Article.discovered_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    return session.execute(query).scalars().all()


def run_extract_cycle(config: WorkerConfig) -> int:
    """One extract cycle: claim articles, extract content, update status."""
    extracted_count = 0

    with SessionLocal() as session:
        articles = claim_articles(session, config.batch_size, config.zombie_timeout_minutes)

        for article in articles:
            if is_shutdown_requested():
                break

            # Mark as being processed (distinct in-progress state).
            article.status = "extracting"
            article.started_at = datetime.now(timezone.utc)
            session.commit()

            try:
                result = extract_article(article.url)

                article.title = result["title"] or article.title
                article.author = result["author"] or article.author
                article.content = result["content"]
                article.content_hash = compute_content_hash(article.content or "")
                # Prefer our extractive summary; fall back to the extractor's.
                summary = result["summary"]
                if not summary and article.content:
                    summary = extractive_summary(article.content)
                article.summary = summary or article.summary
                article.word_count = result["word_count"]
                article.language = detect_language(article.title or article.content)

                # Near-duplicate: same body already ingested from another
                # source/URL. Mark this copy as duplicate (no double NLP/story).
                existing = find_duplicate(session, article.id, article.content_hash)
                if existing:
                    article.duplicate_of_id = existing
                    article.status = "duplicate"
                    article.error_message = None
                    article.started_at = None
                    session.commit()
                    logger.info(
                        "Duplicate content for %s -> article %d", article.url, existing
                    )
                    continue

                article.status = "extracted"
                article.extracted_at = datetime.now(timezone.utc)
                article.error_message = None
                article.started_at = None
                article.retry_count = 0  # fresh budget for the next stage
                # Build transliterated search_vector so MK/SQ Cyrillic is
                # searchable via Latin queries (e.g. "skopje" matches "Скопје").
                raw = f"{article.title or ''} {article.content or ''}"
                article.search_vector = func.to_tsvector("simple", normalize_text(raw))
                extracted_count += 1

                session.commit()
                logger.debug("Extracted: %s", article.title[:60] if article.title else article.url)

            except Exception as e:
                article.retry_count += 1
                article.error_message = str(e)[:500]

                if article.retry_count >= config.max_retries:
                    article.status = "failed"
                    logger.warning("Failed after %d retries: %s", article.retry_count, article.url)
                else:
                    article.status = "fetched"  # reset for retry
                    article.started_at = None

                session.commit()
                logger.debug("Extract error for %s: %s", article.url, e)

    return extracted_count


def run_extract_worker_loop(config: WorkerConfig | None = None) -> None:
    """Main extract worker loop — runs until shutdown signal."""
    config = config or WorkerConfig()
    logger.info("Extract worker started, polling every %ds", config.poll_interval)

    while not is_shutdown_requested():
        try:
            count = run_extract_cycle(config)
            if count:
                logger.info("Extract cycle: %d articles extracted", count)
        except Exception as e:
            logger.error("Extract cycle error: %s", e, exc_info=True)

        for _ in range(config.poll_interval):
            if is_shutdown_requested():
                break

    logger.info("Extract worker stopped")
