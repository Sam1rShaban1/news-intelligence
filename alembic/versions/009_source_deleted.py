"""Migration 009: add soft-delete flag to sources.

Lets operators remove a source from the UI without destroying its historical
articles (which would cascade). Fetching skips sources that are disabled or deleted.
"""

from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("deleted", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_index("idx_sources_enabled", "sources", ["enabled"])
    op.create_index("idx_sources_deleted", "sources", ["deleted"])


def downgrade() -> None:
    op.drop_index("idx_sources_deleted", table_name="sources")
    op.drop_index("idx_sources_enabled", table_name="sources")
    op.drop_column("sources", "deleted")
