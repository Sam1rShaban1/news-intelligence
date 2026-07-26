"""Main entrypoint — runs the worker (scheduler + fetch + extract)."""

import sys

from config.settings import settings
from src.workers.__main__ import main

if __name__ == "__main__":
    main()
