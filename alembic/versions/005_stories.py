"""stories + story_articles — event clustering from entity overlap

Revision ID: 005
Revises: 004
Create Date: 2026-08-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("dominant_sentiment", sa.String(10), nullable=True),
        sa.Column("avg_sentiment_score", sa.Float, nullable=True),
        sa.Column(
            "member_count", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "entity_node_ids",
            ARRAY(sa.Integer),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_stories_last_seen", "stories", ["last_seen"])

    op.create_table(
        "story_articles",
        sa.Column(
            "story_id",
            sa.Integer,
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "article_id",
            sa.Integer,
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("story_articles")
    op.drop_index("idx_stories_last_seen", table_name="stories")
    op.drop_table("stories")
