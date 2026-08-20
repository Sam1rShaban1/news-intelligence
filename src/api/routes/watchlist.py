"""Watchlist routes — journalist-curated entity monitoring.

A watchlist is a single operator's set of entities (people, orgs, places) to keep
an eye on. Each entry is a canonical EntityNode; the dossier-style list endpoint
returns the latest mention stats so the UI can surface "what changed" at a glance.
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.db.models.article import Article
from src.db.models.entity import Entity
from src.db.models.entity_node import EntityNode
from src.db.models.watchlist import WatchlistItem

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchlistAdd(BaseModel):
    node_id: int
    note: str | None = None


@router.get("")
def list_watchlist(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    items = db.execute(
        select(WatchlistItem).order_by(desc(WatchlistItem.created_at)).limit(limit)
    ).scalars().all()
    if not items:
        return {"items": [], "total": 0}

    node_ids = [i.node_id for i in items]
    nodes = db.execute(
        select(EntityNode).where(EntityNode.id.in_(node_ids))
    ).scalars().all()
    node_map = {n.id: n for n in nodes}

    stats = db.execute(
        select(
            Entity.node_id,
            func.count(Entity.id).label("mentions"),
            func.max(Article.discovered_at).label("last_mentioned"),
        )
        .join(Article, Article.id == Entity.article_id)
        .where(
            Entity.node_id.in_(node_ids),
            Article.status.notin_(["failed", "duplicate"]),
        )
        .group_by(Entity.node_id)
    ).all()
    stat_map = {r.node_id: r for r in stats}

    out = []
    for it in items:
        node = node_map.get(it.node_id)
        st = stat_map.get(it.node_id)
        out.append(
            {
                "node_id": it.node_id,
                "note": it.note,
                "created_at": it.created_at.isoformat() if it.created_at else None,
                "entity": {
                    "text": node.canonical_text if node else None,
                    "label": node.label if node else None,
                    "mention_count": node.mention_count if node else 0,
                    "wikidata_id": node.wikidata_id if node else None,
                    "wikidata_url": (
                        f"https://www.wikidata.org/wiki/{node.wikidata_id}"
                        if node and node.wikidata_id
                        else None
                    ),
                },
                "mentions": st.mentions if st else 0,
                "last_mentioned": (
                    st.last_mentioned.isoformat() if st and st.last_mentioned else None
                ),
            }
        )
    return {"items": out, "total": len(out)}


@router.post("")
def add_watchlist(body: WatchlistAdd, db: Session = Depends(get_db)) -> dict:
    node = db.get(EntityNode, body.node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="entity node not found")
    if db.get(WatchlistItem, body.node_id) is not None:
        raise HTTPException(status_code=409, detail="entity already in watchlist")
    item = WatchlistItem(node_id=body.node_id, note=body.note)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {
        "node_id": item.node_id,
        "note": item.note,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.delete("/{node_id}")
def remove_watchlist(
    node_id: int = Path(..., description="EntityNode id"),
    db: Session = Depends(get_db),
) -> dict:
    item = db.get(WatchlistItem, node_id)
    if item is None:
        raise HTTPException(status_code=404, detail="entity not in watchlist")
    db.delete(item)
    db.commit()
    return {"deleted": node_id}
