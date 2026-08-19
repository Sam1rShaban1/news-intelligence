"""Sources route — manage news sources (single-tenant, operator-editable).

Sources are no longer hard-coded in `config/sources.yml`; operators can add,
enable/disable, soft-delete, and test feeds from the UI. The YAML seed remains
only as initial bootstrap. No auth in this build (multi-tenant auth is planned).
"""

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


def _serialize(db: Session, source: Source) -> dict:
    article_count = db.scalar(
        select(func.count(Article.id)).where(Article.source_id == source.id)
    )
    return {
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
    return {"sources": [_serialize(db, s) for s in sources]}


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
    payload: SourceUpdate = None,
    db: Session = Depends(get_db),
) -> dict:
    source = db.get(Source, source_id)
    if source is None or source.deleted:
        raise HTTPException(status_code=404, detail="source not found")
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
        return {"ok": False, "error": str(e)[:500], "entries": []}
    return {"ok": True, "count": len(entries), "sample": entries[:5]}
