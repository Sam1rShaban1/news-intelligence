"""Article embeddings column for semantic (nearest-neighbour) search.

Stored as a portable ARRAY(Float) so `migrate` works on a plain Postgres (incl. the Pi,
which has no `vector` extension). Semantic search computes cosine similarity in Python
over analyzed articles — fully functional without pgvector; swap to pgvector ANN later
if desired.

Revision ID: 014
Revises: 013
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("embedding", sa.ARRAY(sa.Float()), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("articles", "embedded_at")
    op.drop_column("articles", "embedding")
