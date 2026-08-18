"""Article model — a single news article with state machine for pipeline processing."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .source import Source
    from .story import Story


class Article(Base, TimestampMixin):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("url", name="uq_article_url"),
        UniqueConstraint("url_hash", name="uq_article_url_hash"),
        Index("idx_articles_status", "status"),
        Index("idx_articles_source", "source_id"),
        Index("idx_articles_pubdate", "published_date"),
        Index("idx_articles_search", "search_vector", postgresql_using="gin"),
        CheckConstraint("status IN ('new','fetched','extracted','analyzed','failed')"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )

    # URLs
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Content
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    author: Mapped[str | None] = mapped_column(String(300), nullable=True)
    published_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Pipeline state machine
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Pipeline timestamps
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    extracted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Full-text search
    search_vector = mapped_column(TSVECTOR, nullable=True)

    # Sentiment analysis
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_label: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Relationships
    source: Mapped["Source"] = relationship(back_populates="articles")
    entities: Mapped[list["Entity"]] = relationship(  # noqa: F821
        back_populates="article", cascade="all, delete-orphan"
    )
    stories: Mapped[list["Story"]] = relationship(
        secondary="story_articles",
        back_populates="members",
    )

    def __repr__(self) -> str:
        label = (self.title[:40] if self.title else "untitled") if self.title else "untitled"
        return f"<Article {label!r} status={self.status}>"
