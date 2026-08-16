"""Story / event cluster — groups articles about the same event.

Phase 6. A story is a set of articles that share entities within a recent time
window (Jaccard overlap). It lets the knowledge graph resolve into narratives
rather than a flat entity soup.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .article import Article


story_articles = Table(
    "story_articles",
    Base.metadata,
    Column(
        "story_id",
        Integer,
        ForeignKey("stories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "article_id",
        Integer,
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Story(Base, TimestampMixin):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    dominant_sentiment: Mapped[str | None] = mapped_column(String(10), nullable=True)
    avg_sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    member_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    entity_node_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=[], nullable=False)

    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    members: Mapped[list["Article"]] = relationship(
        secondary=story_articles,
        back_populates="stories",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        title = (self.title[:40] if self.title else "untitled") if self.title else "untitled"
        return f"<Story {self.id} {title!r} members={self.member_count}>"
