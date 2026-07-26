"""initial schema — sources and articles tables

Revision ID: 001
Revises:
Create Date: 2026-07-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sources
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("rss_url", sa.String(500), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("article_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # Articles
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "source_id",
            sa.Integer,
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("url_hash", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("author", sa.String(300), nullable=True),
        sa.Column("published_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("word_count", sa.Integer, nullable=True),
        # Pipeline state
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        # Timestamps
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        # Full-text search
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        # Timestamps (from TimestampMixin)
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # Constraints
    op.create_unique_constraint("uq_article_url", "articles", ["url"])
    op.create_unique_constraint("uq_article_url_hash", "articles", ["url_hash"])

    # Indexes
    op.create_index("idx_articles_status", "articles", ["status"])
    op.create_index("idx_articles_source", "articles", ["source_id"])
    op.create_index("idx_articles_pubdate", "articles", ["published_date"])
    op.create_index(
        "idx_articles_search", "articles", ["search_vector"], postgresql_using="gin"
    )

    # Check constraint for status values
    op.create_check_constraint(
        "ck_articles_status",
        "articles",
        "status IN ('new','fetched','extracted','analyzed','failed')",
    )

    # Trigger to auto-populate search_vector from title + content
    # 'simple' config works for Cyrillic, Latin, and Turkish alphabets
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


def downgrade() -> None:
    op.drop_table("articles")
    op.drop_table("sources")
