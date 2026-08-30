"""Alerts API — manage journalist alert rules and browse the alerts they fire."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.db.models.alert import Alert, AlertRule
from src.db.models.article import Article
from src.db.models.entity_node import EntityNode
from src.db.models.source import Source

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertRuleCreate(BaseModel):
    name: str
    query: Optional[str] = None
    languages: Optional[list[str]] = None
    min_sentiment: Optional[float] = None
    entity_node_id: Optional[int] = None
    match_in: str = "both"  # title | content | both
    enabled: bool = True


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    query: Optional[str] = None
    languages: Optional[list[str]] = None
    min_sentiment: Optional[float] = None
    entity_node_id: Optional[int] = None
    match_in: Optional[str] = None
    enabled: Optional[bool] = None


def _serialize_rule(rule: AlertRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "query": rule.query,
        "languages": rule.languages,
        "min_sentiment": rule.min_sentiment,
        "entity_node_id": rule.entity_node_id,
        "match_in": rule.match_in,
        "enabled": rule.enabled,
        "last_checked_at": (
            rule.last_checked_at.isoformat() if rule.last_checked_at else None
        ),
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


@router.get("/rules")
def list_rules(db: Session = Depends(get_db)) -> dict:
    rules = db.execute(select(AlertRule).order_by(desc(AlertRule.created_at))).scalars().all()
    return {"rules": [_serialize_rule(r) for r in rules]}


@router.post("/rules")
def create_rule(body: AlertRuleCreate, db: Session = Depends(get_db)) -> dict:
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    if body.entity_node_id is not None:
        if db.get(EntityNode, body.entity_node_id) is None:
            raise HTTPException(status_code=404, detail="entity node not found")
    if body.match_in not in ("title", "content", "both"):
        raise HTTPException(status_code=400, detail="match_in must be title|content|both")
    rule = AlertRule(
        name=body.name.strip(),
        query=body.query.strip() if body.query else None,
        languages=body.languages,
        min_sentiment=body.min_sentiment,
        entity_node_id=body.entity_node_id,
        match_in=body.match_in,
        enabled=body.enabled,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _serialize_rule(rule)


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int = Path(...), db: Session = Depends(get_db)) -> dict:
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    db.delete(rule)
    db.commit()
    return {"deleted": rule_id}


@router.get("")
def list_alerts(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    query = (
        select(Alert, Article, AlertRule, Source.name.label("source_name"))
        .join(Article, Article.id == Alert.article_id)
        .join(AlertRule, AlertRule.id == Alert.rule_id)
        .join(Source, Source.id == Article.source_id)
    )
    if unread_only:
        query = query.where(Alert.read.is_(False))
    query = query.order_by(desc(Alert.created_at)).limit(limit)
    rows = db.execute(query).all()

    return {
        "alerts": [
            {
                "id": a.id,
                "read": a.read,
                "reason": a.reason,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "rule": {"id": r.id, "name": r.name},
                "article": {
                    "id": art.id,
                    "title": art.title,
                    "url": art.url,
                    "language": art.language,
                    "sentiment_label": art.sentiment_label,
                    "published_date": (
                        art.published_date.isoformat() if art.published_date else None
                    ),
                    "source_name": src_name,
                },
            }
            for a, art, r, src_name in rows
        ]
    }


@router.post("/{alert_id}/read")
def mark_read(
    alert_id: int = Path(...),
    unread: bool = Query(default=False, description="Set to true to mark unread instead"),
    db: Session = Depends(get_db),
) -> dict:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    alert.read = not unread
    db.commit()
    return {"id": alert.id, "read": alert.read}


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db)) -> dict:
    updated = db.execute(
        Alert.__table__.update().where(Alert.read.is_(False)).values(read=True)
    )
    db.commit()
    return {"marked": updated.rowcount}
