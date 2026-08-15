"""Typed relationship triple — subject → predicate → object between two entity nodes."""

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Relationship(Base):
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("entity_nodes.id", ondelete="CASCADE"), nullable=False
    )
    object_node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("entity_nodes.id", ondelete="CASCADE"), nullable=False
    )
    predicate: Mapped[str] = mapped_column(String(50), nullable=False)
    article_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    method: Mapped[str | None] = mapped_column(String(20), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "subject_node_id",
            "object_node_id",
            "predicate",
            "article_id",
            name="uq_relationship_triple",
        ),
        Index("idx_relationships_subject", "subject_node_id"),
        Index("idx_relationships_object", "object_node_id"),
        Index("idx_relationships_predicate", "predicate"),
    )

    def __repr__(self) -> str:
        return f"<Relationship {self.subject_node_id}-{self.predicate}->{self.object_node_id}>"
