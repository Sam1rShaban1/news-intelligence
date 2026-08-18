"""Canonical entity node — deduplicated entity across all articles.

The `entities` table stores raw per-article mentions. `entity_nodes` stores the
canonical, normalized form of each entity so the knowledge graph can merge
surface variants (e.g. "Скопје" and "Skopje") into a single node.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .entity import Entity


class EntityNode(Base, TimestampMixin):
    __tablename__ = "entity_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_text: Mapped[str] = mapped_column(String(500), nullable=False)
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    aliases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    mention_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Wikidata entity linking (see src/nlp/wikidata.py). `external_ids` carries
    # resolved identifiers, e.g. {"wikidata": "Q123", "wikipedia": "..."}.
    wikidata_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    first_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Back-reference to raw mentions
    mentions: Mapped[list["Entity"]] = relationship(back_populates="node")

    __table_args__ = (
        UniqueConstraint("canonical_text", "label", name="uq_entity_node_text_label"),
    )

    def __repr__(self) -> str:
        return f"<EntityNode {self.label}:{self.canonical_text!r} x{self.mention_count}>"
