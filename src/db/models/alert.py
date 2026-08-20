"""Alerts — journalist-defined monitoring rules + the alerts they fire.

A rule watches incoming articles for keywords, a specific entity, a language, or a
sentiment threshold. The `alerts` worker scans newly-analyzed articles and creates
an `Alert` row per match (deduped by rule+article).
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .article import Article
    from .entity_node import EntityNode


class AlertRule(Base, TimestampMixin):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Space/comma separated keywords; an article matches if ANY keyword appears.
    query: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional language filter, e.g. ["mk", "sq"].
    languages: Mapped[list[str] | None] = mapped_column(ARRAY(String(10)), nullable=True)
    # Alert when sentiment_score <= min_sentiment (use negative values for "bad news").
    min_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Restrict to articles mentioning this canonical entity (EntityNode id).
    entity_node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("entity_nodes.id", ondelete="CASCADE"), nullable=True
    )
    # Where to look for keywords: title | content | both.
    match_in: Mapped[str] = mapped_column(String(10), default="both", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Set by the worker after each scan so it only looks at new articles.
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<AlertRule {self.name!r} enabled={self.enabled}>"


class Alert(Base, TimestampMixin):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("rule_id", "article_id", name="uq_alert_rule_article"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False
    )
    article_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    rule: Mapped["AlertRule"] = relationship(back_populates="alerts")
    article: Mapped["Article"] = relationship("Article")

    def __repr__(self) -> str:
        return f"<Alert rule={self.rule_id} article={self.article_id} read={self.read}>"
