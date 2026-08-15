"""Entity co-occurrence edge — weight = number of articles both entities appear in.

Undirected: a pair (a, b) is stored once with node_a_id < node_b_id.
"""

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class EntityEdge(Base):
    __tablename__ = "entity_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_a_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("entity_nodes.id", ondelete="CASCADE"), nullable=False
    )
    node_b_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("entity_nodes.id", ondelete="CASCADE"), nullable=False
    )
    weight: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("node_a_id", "node_b_id", name="uq_entity_edge_pair"),
        Index("idx_entity_edges_a", "node_a_id"),
        Index("idx_entity_edges_b", "node_b_id"),
    )

    def __repr__(self) -> str:
        return f"<EntityEdge {self.node_a_id}-{self.node_b_id} w={self.weight}>"
