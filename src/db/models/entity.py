"""Entity model — named entities extracted from articles."""

from typing import TYPE_CHECKING

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .article import Article
    from .entity_node import EntityNode


class Entity(Base, TimestampMixin):
    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint(
            "article_id", "text", "label", name="uq_entity_article_text_label"
        ),
        Index("idx_entities_article", "article_id"),
        Index("idx_entities_label", "label"),
        Index("idx_entities_text", "text"),
        Index("idx_entities_node", "node_id"),
        Index("idx_entities_norm", "normalized_text"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )

    # Entity data
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    label: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # PER, ORG, LOC, MISC, EVENT, etc.
    start_pos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_pos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Normalized form + link to canonical node
    normalized_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    node_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("entity_nodes.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    article: Mapped["Article"] = relationship(back_populates="entities")
    node: Mapped["EntityNode"] = relationship(back_populates="mentions")

    def __repr__(self) -> str:
        return f"<Entity {self.label}:{self.text!r}>"
