"""Sources route — manage news sources (single-tenant, operator-editable).

Sources are no longer hard-coded in `config/sources.yml`; operators can add,
enable/disable, soft-delete, and test feeds from the UI. The YAML seed remains
only as initial bootstrap. No auth in this build (multi-tenant auth is planned).
"""

import logging
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.collector.fetcher import discover_articles
from src.collector.ssrf import is_safe_url
from src.db.models.article import Article
from src.db.models.source import Source

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceCreate(BaseModel):
    name: str
    url: str
    rss_url: str | None = None
    enabled: bool = True


class SourceUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    rss_url: str | None = None
    enabled: bool | None = None


def _credibility_map(db: Session) -> dict[int, dict]:
    """Compute reliability signals per source from article outcome counts.

    Returns {source_id: {articles_total, failed, duplicate, success,
    failure_rate, duplicate_rate, reliability}}.
    """
    rows = db.execute(
        select(
            Article.source_id,
            func.count(Article.id).label("total"),
            func.count(Article.id).filter(Article.status == "failed").label("failed"),
            func.count(Article.id).filter(Article.status == "duplicate").label("duplicate"),
        ).group_by(Article.source_id)
    ).all()
    out: dict[int, dict] = {}
    for r in rows:
        total = r.total or 0
        failed = r.failed or 0
        dup = r.duplicate or 0
        failure_rate = failed / total if total else 0.0
        dup_rate = dup / total if total else 0.0
        reliability = (1 - failure_rate) * (1 - dup_rate)
        out[r.source_id] = {
            "articles_total": total,
            "failed": failed,
            "duplicate": dup,
            "success": total - failed - dup,
            "failure_rate": round(failure_rate, 4),
            "duplicate_rate": round(dup_rate, 4),
            "reliability": round(reliability, 4),
        }
    return out


def _score_source(source: Source, stats: dict | None) -> dict:
    """Combine reliability with feed-recency into a 0-100 credibility score."""
    now = datetime.now(timezone.utc)
    reliability = stats["reliability"] if stats else 0.0
    if source.last_scanned_at is None:
        recency = 0.7  # unknown — slight penalty, not a hard fail
    else:
        days = (now - source.last_scanned_at).days
        recency = max(0.5, 1 - days / 30.0)
    score = round(100.0 * reliability * recency, 1)
    grade = (
        "A" if score >= 85 else
        "B" if score >= 70 else
        "C" if score >= 50 else
        "D" if score >= 30 else "F"
    )
    return {
        "score": score,
        "grade": grade,
        "recency_factor": round(recency, 4),
        "articles_total": stats["articles_total"] if stats else 0,
        "failed": stats["failed"] if stats else 0,
        "duplicate": stats["duplicate"] if stats else 0,
        "failure_rate": stats["failure_rate"] if stats else 0.0,
        "duplicate_rate": stats["duplicate_rate"] if stats else 0.0,
    }


def _serialize(db: Session, source: Source, cred: dict[int, dict] | None = None) -> dict:
    article_count = db.scalar(
        select(func.count(Article.id)).where(Article.source_id == source.id)
    )
    result = {
        "id": source.id,
        "name": source.name,
        "url": source.url,
        "rss_url": source.rss_url,
        "enabled": source.enabled,
        "deleted": source.deleted,
        "article_count": article_count or 0,
        "error_count": source.error_count,
        "last_error": source.last_error,
        "last_scanned_at": (
            source.last_scanned_at.isoformat() if source.last_scanned_at else None
        ),
    }
    if cred is not None:
        result["credibility"] = _score_source(source, cred.get(source.id))
    return result


@router.get("")
def list_sources(
    enabled: bool | None = Query(default=None, description="Filter by enabled flag"),
    include_deleted: bool = Query(default=False, description="Include soft-deleted sources"),
    db: Session = Depends(get_db),
) -> dict:
    query = select(Source)
    if not include_deleted:
        query = query.where(Source.deleted.is_(False))
    if enabled is not None:
        query = query.where(Source.enabled.is_(enabled))
    sources = db.execute(query.order_by(Source.name)).scalars().all()
    cred = _credibility_map(db)
    return {"sources": [_serialize(db, s, cred) for s in sources]}


@router.get("/credibility")
def source_credibility(db: Session = Depends(get_db)) -> dict:
    """Credibility scoring across all sources: reliability (failure/duplicate rates)
    combined with feed-recency into a 0-100 score and letter grade."""
    sources = db.execute(select(Source).order_by(Source.name)).scalars().all()
    cred = _credibility_map(db)
    return {
        "sources": [
            {
                "id": s.id,
                "name": s.name,
                "enabled": s.enabled,
                "credibility": _score_source(s, cred.get(s.id)),
            }
            for s in sources
        ]
    }


@router.post("")
def create_source(payload: SourceCreate, db: Session = Depends(get_db)) -> dict:
    if not is_safe_url(payload.url) or (payload.rss_url and not is_safe_url(payload.rss_url)):
        raise HTTPException(status_code=400, detail="URL must be http(s) and publicly reachable")
    exists = db.execute(
        select(Source).where(Source.url == payload.url)
    ).scalar()
    if exists:
        raise HTTPException(status_code=400, detail="A source with this URL already exists")
    source = Source(
        name=payload.name,
        url=payload.url,
        rss_url=payload.rss_url,
        enabled=payload.enabled,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return _serialize(db, source)


@router.patch("/{source_id}")
def update_source(
    source_id: int = Path(..., description="Source id"),
    payload: SourceUpdate | None = None,
    db: Session = Depends(get_db),
) -> dict:
    source = db.get(Source, source_id)
    if source is None or source.deleted:
        raise HTTPException(status_code=404, detail="source not found")
    payload = payload or SourceUpdate()
    if payload.url is not None:
        if not is_safe_url(payload.url):
            raise HTTPException(status_code=400, detail="URL must be http(s) and reachable")
        dup = db.execute(
            select(Source).where(Source.url == payload.url, Source.id != source_id)
        ).scalar()
        if dup:
            raise HTTPException(status_code=400, detail="A source with this URL already exists")
        source.url = payload.url
    if payload.name is not None:
        source.name = payload.name
    if payload.rss_url is not None:
        if payload.rss_url and not is_safe_url(payload.rss_url):
            raise HTTPException(status_code=400, detail="RSS URL must be http(s) and reachable")
        source.rss_url = payload.rss_url
    if payload.enabled is not None:
        source.enabled = payload.enabled
    db.commit()
    return _serialize(db, source)


@router.delete("/{source_id}")
def delete_source(
    source_id: int = Path(..., description="Source id"),
    db: Session = Depends(get_db),
) -> dict:
    """Soft-delete: stop fetching and hide from the default list, but keep articles."""
    source = db.get(Source, source_id)
    if source is None or source.deleted:
        raise HTTPException(status_code=404, detail="source not found")
    source.deleted = True
    source.enabled = False
    db.commit()
    return {"id": source.id, "deleted": True}


@router.post("/{source_id}/test")
def test_source(
    source_id: int = Path(..., description="Source id"),
    db: Session = Depends(get_db),
) -> dict:
    """Validate that the source actually yields articles (fetches the feed once)."""
    source = db.get(Source, source_id)
    if source is None or source.deleted:
        raise HTTPException(status_code=404, detail="source not found")
    if not is_safe_url(source.url) or (source.rss_url and not is_safe_url(source.rss_url)):
        return {"ok": False, "error": "URL is not http(s) or not publicly reachable", "entries": []}
    probe = SimpleNamespace(name=source.name, url=source.url, rss_url=source.rss_url)
    try:
        entries = discover_articles(probe)
    except Exception as e:  # surface any discovery failure to the UI
        logger.warning("Source test failed for %s: %s", source.name, e)
        return {
            "ok": False,
            "error": "fetch failed; check the source URL and connectivity",
            "entries": [],
        }
    return {"ok": True, "count": len(entries), "sample": entries[:5]}
