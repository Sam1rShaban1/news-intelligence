"""Main worker entrypoint — runs scheduler + fetch + extract + analyze workers concurrently."""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor

from config.settings import settings
from src.scheduler.scheduler import run_scheduler
from src.workers.analyze import run_analyze_worker_loop
from src.workers.extract import run_extract_worker_loop
from src.workers.fetch import run_fetch_worker_loop
from src.workers.lifecycle import WorkerConfig, install_signal_handlers, is_shutdown_requested

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main() -> None:
    install_signal_handlers()
    logger.info("News Intelligence worker starting...")

    config = WorkerConfig(
        poll_interval=5,
        batch_size=settings.batch_size,
        zombie_timeout_minutes=settings.zombie_timeout_minutes,
        max_retries=settings.max_retries,
    )

    # Run all workers concurrently
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="worker") as executor:
        executor.submit(run_scheduler, config)
        executor.submit(run_fetch_worker_loop, config)
        executor.submit(run_extract_worker_loop, config)
        executor.submit(run_analyze_worker_loop, config)

        # Block until shutdown signal
        while not is_shutdown_requested():
            pass

        logger.info("Shutting down worker threads...")


if __name__ == "__main__":
    main()
