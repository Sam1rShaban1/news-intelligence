"""Watchlist — journalist-curated entities to monitor (single-operator, no authz)."""

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class WatchlistItem(Base, TimestampMixin):
    __tablename__ = "watchlist_items"

    # The watched entity is a canonical EntityNode; removing the node cascades here.
    node_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("entity_nodes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    node: Mapped["EntityNode"] = relationship("EntityNode")  # noqa: F821

    def __repr__(self) -> str:
        return f"<WatchlistItem node_id={self.node_id}>"
