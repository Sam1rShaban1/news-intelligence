"""FastAPI application entrypoint."""

import logging
import sys

import uvicorn
from fastapi import FastAPI

from config.settings import settings
from src.api.routes import articles_router, health_router, search_router

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="News Intelligence API",
        version="0.1.0",
        description="Self-hosted news analysis platform",
    )
    app.include_router(health_router)
    app.include_router(articles_router)
    app.include_router(search_router)

    @app.on_event("startup")
    def on_startup() -> None:
        logger.info("API starting on port 8000")

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)
