"""knowledge graph — entity nodes, co-occurrence edges, sentiment_done status

Revision ID: 003
Revises: 002
Create Date: 2026-07-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── entities: add normalized form (no FK yet) ──
    op.add_column("entities", sa.Column("normalized_text", sa.String(500), nullable=True))
    op.create_index("idx_entities_norm", "entities", ["normalized_text"])

    # ── entity_nodes: canonical deduplicated entities (created BEFORE the FK) ──
    op.create_table(
        "entity_nodes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("canonical_text", sa.String(500), nullable=False),
        sa.Column("label", sa.String(20), nullable=False),
        sa.Column("aliases", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("mention_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_unique_constraint(
        "uq_entity_node_text_label", "entity_nodes", ["canonical_text", "label"]
    )

    # ── entities.node_id: now safe to add the FK to entity_nodes ──
    op.add_column(
        "entities",
        sa.Column(
            "node_id",
            sa.Integer,
            sa.ForeignKey("entity_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_entities_node", "entities", ["node_id"])

    # ── entity_edges: co-occurrence graph ──
    op.create_table(
        "entity_edges",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "node_a_id",
            sa.Integer,
            sa.ForeignKey("entity_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "node_b_id",
            sa.Integer,
            sa.ForeignKey("entity_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("weight", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_unique_constraint("uq_entity_edge_pair", "entity_edges", ["node_a_id", "node_b_id"])
    op.create_index("idx_entity_edges_a", "entity_edges", ["node_a_id"])
    op.create_index("idx_entity_edges_b", "entity_edges", ["node_b_id"])

    # ── status enum: add 'sentiment_done' (sentiment computed, awaiting NER) ──
    op.drop_constraint("ck_articles_status", "articles", type_="check")
    op.create_check_constraint(
        "ck_articles_status",
        "articles",
        "status IN ('new','fetched','extracted','sentiment_done','analyzed','failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_articles_status", "articles", type_="check")
    op.create_check_constraint(
        "ck_articles_status",
        "articles",
        "status IN ('new','fetched','extracted','analyzed','failed')",
    )
    op.drop_table("entity_edges")
    op.drop_table("entity_nodes")
    op.drop_index("idx_entities_node", "entities")
    op.drop_column("entities", "node_id")
    op.drop_index("idx_entities_norm", "entities")
    op.drop_column("entities", "normalized_text")
