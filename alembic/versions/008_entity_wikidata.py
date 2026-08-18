"""entity wikidata linking — add external-id columns to entity_nodes

Revision ID: 008
Revises: 007
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entity_nodes",
        sa.Column("wikidata_id", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "entity_nodes",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "entity_nodes",
        sa.Column("external_ids", sa.JSON(), nullable=True),
    )
    op.create_index(
        "idx_entity_nodes_wikidata", "entity_nodes", ["wikidata_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_entity_nodes_wikidata", table_name="entity_nodes")
    op.drop_column("entity_nodes", "external_ids")
    op.drop_column("entity_nodes", "description")
    op.drop_column("entity_nodes", "wikidata_id")
