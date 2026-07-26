"""Scheduler — periodically triggers article discovery for all enabled sources."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config.settings import settings
from src.workers.fetch import run_fetch_cycle
from src.workers.lifecycle import WorkerConfig, is_shutdown_requested

logger = logging.getLogger(__name__)


def _scheduled_fetch() -> None:
    """Called by APScheduler on each interval."""
    logger.info("Scheduled fetch triggered")
    try:
        count = run_fetch_cycle(WorkerConfig())
        logger.info("Scheduled fetch completed: %d new articles", count)
    except Exception as e:
        logger.error("Scheduled fetch failed: %s", e, exc_info=True)


def run_scheduler(config: WorkerConfig | None = None) -> None:
    """
    Start APScheduler and run until shutdown.
    On startup, does an immediate fetch. Then repeats every `scan_interval_minutes`.
    """
    config = config or WorkerConfig()

    # Immediate first fetch
    logger.info("Running initial fetch on startup...")
    try:
        count = run_fetch_cycle(config)
        logger.info("Startup fetch complete: %d new articles", count)
    except Exception as e:
        logger.error("Startup fetch failed: %s", e, exc_info=True)

    # Set up periodic scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _scheduled_fetch,
        trigger=IntervalTrigger(minutes=settings.scan_interval_minutes),
        id="periodic_fetch",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started — fetching every %d minutes", settings.scan_interval_minutes
    )

    # Block until shutdown
    while not is_shutdown_requested():
        pass

    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")
