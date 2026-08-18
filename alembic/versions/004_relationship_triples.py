"""relationship triples — typed subject/predicate/object edges

Revision ID: 004
Revises: 003
Create Date: 2026-08-15
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "relationships",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "subject_node_id",
            sa.Integer,
            sa.ForeignKey("entity_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "object_node_id",
            sa.Integer,
            sa.ForeignKey("entity_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("predicate", sa.String(50), nullable=False),
        sa.Column(
            "article_id",
            sa.Integer,
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("method", sa.String(20), nullable=True),
    )
    op.create_unique_constraint(
        "uq_relationship_triple",
        "relationships",
        ["subject_node_id", "object_node_id", "predicate", "article_id"],
    )
    op.create_index("idx_relationships_subject", "relationships", ["subject_node_id"])
    op.create_index("idx_relationships_object", "relationships", ["object_node_id"])
    op.create_index("idx_relationships_predicate", "relationships", ["predicate"])


def downgrade() -> None:
    op.drop_table("relationships")
