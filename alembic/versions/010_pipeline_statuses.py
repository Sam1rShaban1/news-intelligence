"""Add in-progress pipeline statuses (extracting / analyzing / ner_running).

Revision ID: 010
Revises: 009
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_CONSTRAINT = (
    "status IN ('new','fetched','extracting','extracted','analyzing',"
    "'sentiment_done','ner_running','analyzed','failed')"
)
_OLD_CONSTRAINT = (
    "status IN ('new','fetched','extracted','analyzed','sentiment_done','failed')"
)


def upgrade() -> None:
    bind = op.get_bind()
    # Drop whatever check constraint currently guards articles.status (its auto
    # generated name varies), then install the named one with the new states.
    names = bind.execute(
        sa.text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'articles'::regclass AND contype = 'c'"
        )
    ).fetchall()
    for (name,) in names:
        op.drop_constraint(name, "articles", type_="check")

    op.create_check_constraint("ck_article_status", "articles", sa.text(_NEW_CONSTRAINT))


def downgrade() -> None:
    op.drop_constraint("ck_article_status", "articles", type_="check")
    op.create_check_constraint("ck_article_status", "articles", sa.text(_OLD_CONSTRAINT))
