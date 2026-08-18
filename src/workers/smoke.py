"""One-shot smoke test — runs the full pipeline once on live feeds.

Usage:
  # Quick validation (ingestion + extraction + sentiment + language detection),
  # no model load. Safe to run on the `worker` container:
  docker compose run --rm worker -m src.workers.smoke

  # Full validation incl. NER + knowledge graph. Downloads GLiNER2 once (~27 min on
  # first run) into the `hf_cache` volume and warms it. Run on the `ner` container:
  NEWS_SMOKE_NER=1 docker compose run --rm ner -m src.workers.smoke

Env:
  NEWS_SMOKE_SOURCES  int  limit how many enabled sources to fetch (default: all)
  NEWS_SMOKE_NER      "1"  also run the NER + graph stage (needs the model)
  NEWS_SMOKE_ITERS    int  max per-stage drain iterations (default 10)
"""

import logging
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import func, select

from config.settings import settings
from src.collector.fetcher import discover_articles
from src.db.models.article import Article
from src.db.models.entity import Entity
from src.db.models.entity_edge import EntityEdge
from src.db.models.entity_node import EntityNode
from src.db.models.relationship import Relationship
from src.db.models.source import Source
from src.db.session import SessionLocal
from src.workers.analyze import run_analyze_cycle
from src.workers.extract import run_extract_cycle
from src.workers.fetch import _process_source, run_fetch_cycle
from src.workers.lifecycle import WorkerConfig
from src.workers.ner_service import run_ner_cycle

logger = logging.getLogger("smoke")


def _drain(cycle_fn, config: WorkerConfig, max_iterations: int) -> int:
    total = 0
    for _ in range(max_iterations):
        n = cycle_fn(config)
        total += n
        if n == 0:
            break
    return total


def _bounded_fetch(config: WorkerConfig, limit_sources: int | None) -> int:
    """Fetch all enabled sources, or only the first `limit_sources` if set."""
    if not limit_sources:
        return run_fetch_cycle(config)

    total = 0
    with SessionLocal() as session:
        sources = session.execute(
            select(Source).where(Source.enabled.is_(True)).limit(limit_sources)
        ).scalars().all()
        for src in sources:
            try:
                entries = discover_articles(src)
                total += _process_source(session, src, entries)
                src.last_scanned_at = datetime.now(timezone.utc)
                src.last_error = None
                session.commit()
            except Exception as e:  # keep going through bad sources
                    src.error_count += 1
                    src.last_error = str(e)[:500]
                    session.commit()
                    logger.warning("Fetch failed for %s: %s", src.name, e)
    return total


def run_smoke(
    limit_sources: int | None = None,
    include_ner: bool = False,
    max_iterations: int = 10,
    batch_size: int = 10,
) -> dict:
    config = WorkerConfig(
        poll_interval=1,
        batch_size=batch_size,
        zombie_timeout_minutes=settings.zombie_timeout_minutes,
        max_retries=settings.max_retries,
    )
    logger.info(
        "Smoke run starting (limit_sources=%s, include_ner=%s, iters=%s)",
        limit_sources, include_ner, max_iterations,
    )

    fetched = _bounded_fetch(config, limit_sources)
    logger.info("Fetch: %d new articles", fetched)
    _drain(run_extract_cycle, config, max_iterations)
    _drain(run_analyze_cycle, config, max_iterations)
    if include_ner:
        _drain(run_ner_cycle, config, max_iterations)

    with SessionLocal() as session:
        counts = {
            "articles_total": session.scalar(select(func.count(Article.id))) or 0,
            "articles_analyzed": session.scalar(
                select(func.count(Article.id)).where(Article.status == "analyzed")
            ) or 0,
            "articles_failed": session.scalar(
                select(func.count(Article.id)).where(Article.status == "failed")
            ) or 0,
            "entities": session.scalar(select(func.count(Entity.id))) or 0,
            "entity_nodes": session.scalar(select(func.count(EntityNode.id))) or 0,
            "entity_edges": session.scalar(select(func.count(EntityEdge.id))) or 0,
            "relationships": session.scalar(select(func.count(Relationship.id))) or 0,
        }
        sample = session.execute(
            select(Relationship.predicate, func.count(Relationship.id))
            .group_by(Relationship.predicate)
            .order_by(func.count(Relationship.id).desc())
        ).all()
    counts["relationships_by_predicate"] = {r.predicate: r[1] for r in sample}

    print("\n=== SMOKE TEST SUMMARY ===")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    logger.info("SMOKE SUMMARY: %s", counts)
    return counts


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    limit = os.getenv("NEWS_SMOKE_SOURCES")
    limit = int(limit) if limit and limit.isdigit() else None
    include_ner = os.getenv("NEWS_SMOKE_NER", "0") == "1"
    iters = os.getenv("NEWS_SMOKE_ITERS")
    iters = int(iters) if iters and iters.isdigit() else 10
    run_smoke(limit_sources=limit, include_ner=include_ner, max_iterations=iters)


if __name__ == "__main__":
    main()
