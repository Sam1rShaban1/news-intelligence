"""Worker lifecycle management — graceful shutdown and configuration."""

import logging
import signal
from dataclasses import dataclass
from threading import Event

logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    poll_interval: int = 5  # seconds between polls
    batch_size: int = 30  # articles per claim
    zombie_timeout_minutes: int = 5  # stuck task threshold
    max_retries: int = 3


shutdown_event = Event()


def handle_shutdown(signum: int, frame: object) -> None:
    logger.info("Received signal %s, shutting down gracefully...", signal.Signals(signum).name)
    shutdown_event.set()


def install_signal_handlers() -> None:
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)


def is_shutdown_requested() -> bool:
    return shutdown_event.is_set()
