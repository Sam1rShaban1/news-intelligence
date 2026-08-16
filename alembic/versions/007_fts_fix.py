"""drop search_vector trigger — Python now owns tsvector generation

Revision ID: 007
Revises: 006
Create Date: 2026-08-16
"""
from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The PL/pgSQL trigger built search_vector from raw title+content —
    # couldn't transliterate Cyrillic. Move tsvector generation to the Python
    # extract worker (which uses normalize_text) so MK/SQ are searchable via
    # Latin queries.
    op.execute("DROP TRIGGER IF EXISTS trg_articles_search_vector ON articles")
    op.execute("DROP FUNCTION IF EXISTS articles_search_vector_update()")


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION articles_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('simple',
                coalesce(NEW.title, '') || ' ' || coalesce(NEW.content, '')
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_articles_search_vector
            BEFORE INSERT OR UPDATE OF title, content
            ON articles
            FOR EACH ROW
            EXECUTE FUNCTION articles_search_vector_update();
    """)
