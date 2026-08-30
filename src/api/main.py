"""FastAPI application entrypoint."""

import logging
import sys
from typing import List

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from src.api.deps import require_api_key
from src.api.routes import articles_router, health_router, search_router
from src.api.routes.alerts import router as alerts_router
from src.api.routes.analytics import router as analytics_router
from src.api.routes.entities import router as entities_router
from src.api.routes.export import router as export_router
from src.api.routes.graph import router as graph_router
from src.api.routes.sentiment import router as sentiment_router
from src.api.routes.sources import router as sources_router
from src.api.routes.stories import router as stories_router
from src.api.routes.watchlist import router as watchlist_router

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _parse_origins(raw: str) -> List[str]:
    if raw.strip() == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app() -> FastAPI:
    app = FastAPI(
        title="News Intelligence API",
        version="0.1.0",
        description="Self-hosted news analysis platform",
    )

    origins = _parse_origins(settings.cors_origins)
    # A wildcard origin must not be combined with credentials (browsers reject it
    # and Starlette would otherwise reflect arbitrary origins).
    allow_credentials = origins != ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth is opt-in via NEWS_API_KEY; health is always public.
    app.include_router(health_router)
    app.include_router(articles_router, dependencies=[Depends(require_api_key)])
    app.include_router(search_router, dependencies=[Depends(require_api_key)])
    app.include_router(analytics_router, dependencies=[Depends(require_api_key)])
    app.include_router(entities_router, dependencies=[Depends(require_api_key)])
    app.include_router(sentiment_router, dependencies=[Depends(require_api_key)])
    app.include_router(graph_router, dependencies=[Depends(require_api_key)])
    app.include_router(sources_router, dependencies=[Depends(require_api_key)])
    app.include_router(stories_router, dependencies=[Depends(require_api_key)])
    app.include_router(export_router, dependencies=[Depends(require_api_key)])
    app.include_router(watchlist_router, dependencies=[Depends(require_api_key)])
    app.include_router(alerts_router, dependencies=[Depends(require_api_key)])

    @app.on_event("startup")
    def on_startup() -> None:
        logger.info("API starting on port 8000")

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)
