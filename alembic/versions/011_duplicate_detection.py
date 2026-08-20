"""Near-duplicate detection: duplicate_of_id + 'duplicate' status.

Revision ID: 011
Revises: 010
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS_ALL = (
    "status IN ('new','fetched','extracting','extracted','analyzing',"
    "'sentiment_done','ner_running','analyzed','failed','duplicate')"
)
_STATUS_PREV = (
    "status IN ('new','fetched','extracting','extracted','analyzing',"
    "'sentiment_done','ner_running','analyzed','failed')"
)


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("duplicate_of_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_articles_duplicate_of",
        "articles",
        "articles",
        ["duplicate_of_id"],
        ["id"],
        ondelete="SET NULL",
    )

    bind = op.get_bind()
    names = bind.execute(
        sa.text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'articles'::regclass AND contype = 'c'"
        )
    ).fetchall()
    for (name,) in names:
        op.drop_constraint(name, "articles", type_="check")
    op.create_check_constraint("ck_article_status", "articles", sa.text(_STATUS_ALL))


def downgrade() -> None:
    op.drop_constraint("fk_articles_duplicate_of", "articles", type_="foreignkey")
    op.drop_column("articles", "duplicate_of_id")

    op.drop_constraint("ck_article_status", "articles", type_="check")
    op.create_check_constraint("ck_article_status", "articles", sa.text(_STATUS_PREV))
