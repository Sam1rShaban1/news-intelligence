"""Alerts worker — scans newly analyzed articles against journalist alert rules.

Runs as its own service (`python -m src.workers.alerts_service`). For each enabled
rule it looks at articles analyzed since the rule was last checked and creates an
`Alert` when a keyword, watched entity, language, or sentiment threshold matches.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select

from config.settings import settings
from src.db.models.alert import Alert, AlertRule
from src.db.models.article import Article
from src.db.models.entity import Entity
from src.db.session import SessionLocal
from src.workers.lifecycle import WorkerConfig, install_signal_handlers, is_shutdown_requested

logger = logging.getLogger(__name__)


def _match_subquery(rule: AlertRule, since: datetime | None):
    from sqlalchemy.sql import exists as sql_exists

    q = select(Article).where(Article.status == "analyzed")
    if since is not None:
        q = q.where(Article.analyzed_at > since)
    if rule.languages:
        q = q.where(Article.language.in_(rule.languages))
    if rule.min_sentiment is not None:
        q = q.where(
            Article.sentiment_score.isnot(None),
            Article.sentiment_score <= rule.min_sentiment,
        )
    if rule.entity_node_id is not None:
        q = q.where(
            sql_exists().where(
                Entity.article_id == Article.id,
                Entity.node_id == rule.entity_node_id,
            )
        )
    terms = [t.strip() for t in (rule.query or "").replace(",", " ").split() if t.strip()]
    if terms:
        cols = []
        if rule.match_in in ("title", "both"):
            cols.append(Article.title)
        if rule.match_in in ("content", "both"):
            cols.append(Article.content)
        if cols:
            conds = [c.ilike(f"%{t}%") for t in terms for c in cols]
            q = q.where(or_(*conds))
    return q


def _reason(rule: AlertRule) -> str:
    parts = []
    if rule.query:
        parts.append(f"matched keywords: {rule.query}")
    if rule.entity_node_id is not None:
        parts.append(f"mentions watched entity #{rule.entity_node_id}")
    if rule.min_sentiment is not None:
        parts.append(f"sentiment <= {rule.min_sentiment}")
    if rule.languages:
        parts.append(f"language in {','.join(rule.languages)}")
    return "; ".join(parts) or "rule match"


def run_alerts_cycle(config: WorkerConfig) -> int:
    """One alert scan pass over all enabled rules. Returns alerts created."""
    created = 0
    with SessionLocal() as db:
        rules = db.execute(
            select(AlertRule).where(AlertRule.enabled.is_(True))
        ).scalars().all()
        if not rules:
            return 0

        now = datetime.now(timezone.utc)
        for rule in rules:
            since = rule.last_checked_at
            candidates = db.execute(
                _match_subquery(rule, since).limit(500)
            ).scalars().all()
            if not candidates:
                rule.last_checked_at = now
                continue

            ids = [a.id for a in candidates]
            existing = set(
                r[0] for r in db.execute(
                    select(Alert.article_id).where(
                        Alert.rule_id == rule.id, Alert.article_id.in_(ids)
                    )
                ).all()
            )
            reason = _reason(rule)
            for a in candidates:
                if a.id in existing:
                    continue
                db.add(Alert(rule_id=rule.id, article_id=a.id, reason=reason))
                created += 1
                existing.add(a.id)
            rule.last_checked_at = now
        db.commit()
    return created


def run_alerts_worker_loop(config: WorkerConfig | None = None) -> None:
    if not settings.feature_alerts:
        logger.warning("FEATURE_ALERTS is disabled — alerts worker will not run. Exiting.")
        return
    config = config or WorkerConfig()
    logger.info("Alerts worker started, scanning every %ds", config.poll_interval)
    while not is_shutdown_requested():
        try:
            n = run_alerts_cycle(config)
            if n:
                logger.info("Alerts cycle: %d new alert(s)", n)
        except Exception as e:
            logger.error("Alerts cycle error: %s", e, exc_info=True)
        for _ in range(config.poll_interval):
            if is_shutdown_requested():
                break
    logger.info("Alerts worker stopped")


def main() -> None:
    install_signal_handlers()
    logger.info("Alerts worker starting...")
    run_alerts_worker_loop()


if __name__ == "__main__":
    main()
