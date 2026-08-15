"""add entities table and sentiment columns

Revision ID: 002
Revises: 001
Create Date: 2026-07-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add sentiment columns to articles
    op.add_column("articles", sa.Column("sentiment_score", sa.Float, nullable=True))
    op.add_column("articles", sa.Column("sentiment_label", sa.String(10), nullable=True))

    # Create entities table
    op.create_table(
        "entities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "article_id",
            sa.Integer,
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.String(500), nullable=False),
        sa.Column("label", sa.String(20), nullable=False),
        sa.Column("start_pos", sa.Integer, nullable=True),
        sa.Column("end_pos", sa.Integer, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # Entity constraints and indexes
    op.create_unique_constraint(
        "uq_entity_article_text_label", "entities", ["article_id", "text", "label"]
    )
    op.create_index("idx_entities_article", "entities", ["article_id"])
    op.create_index("idx_entities_label", "entities", ["label"])
    op.create_index("idx_entities_text", "entities", ["text"])


def downgrade() -> None:
    op.drop_table("entities")
    op.drop_column("articles", "sentiment_label")
    op.drop_column("articles", "sentiment_score")
