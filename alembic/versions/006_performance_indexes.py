"""performance indexes — knowledge-graph / story / analytics queries

Revision ID: 006
Revises: 005
Create Date: 2026-08-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Story candidate scan uses `entity_node_ids && :ids` — needs a GIN index.
    op.create_index(
        "idx_stories_entity_ids",
        "stories",
        ["entity_node_ids"],
        postgresql_using="gin",
    )
    op.create_index("idx_stories_language", "stories", ["language"])
    op.create_index("idx_stories_dominant", "stories", ["dominant_sentiment"])

    # Knowledge-graph "top nodes" and co-occurrence edges are ordered by these
    # columns; a descending index lets the LIMIT avoid a full sort.
    op.create_index(
        "idx_entity_nodes_label_mention",
        "entity_nodes",
        ["label", sa.text("mention_count DESC")],
    )
    op.create_index("idx_entity_edges_weight", "entity_edges", [sa.text("weight DESC")])

    # Article-language / sentiment filters used by explore + analytics.
    op.create_index("idx_articles_language", "articles", ["language"])
    op.create_index("idx_articles_sentiment_label", "articles", ["sentiment_label"])


def downgrade() -> None:
    op.drop_index("idx_articles_sentiment_label", table_name="articles")
    op.drop_index("idx_articles_language", table_name="articles")
    op.drop_index("idx_entity_edges_weight", table_name="entity_edges")
    op.drop_index("idx_entity_nodes_label_mention", table_name="entity_nodes")
    op.drop_index("idx_stories_dominant", table_name="stories")
    op.drop_index("idx_stories_language", table_name="stories")
    op.drop_index("idx_stories_entity_ids", table_name="stories", postgresql_using="gin")
