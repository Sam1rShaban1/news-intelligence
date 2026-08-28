"""Migration-vs-models drift guard (no real fetch; uses a throwaway database).

Runs ``alembic upgrade head`` into a temporary database and compares the
resulting schema against the SQLAlchemy ``Base.metadata``. If a model table or
column exists in code but not in the migrations, this test fails — catching the
model/migration drift that the create_all-based suite would otherwise hide.

Requires a Postgres where the test role can ``CREATE DATABASE``; if not, the test
is skipped (grant CREATEDB to enable it).
"""

import os
import time

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from src.db.models import Base

MIG_DB = "news_intelligence_mig_check"


def _admin_engine():
    url = os.environ.get(
        "NEWS_DATABASE_URL",
        "postgresql://news:news@localhost:5432/news_intelligence",
    )
    # Connect without selecting a specific database so we can CREATE/DROP one.
    return create_engine(url, isolation_level="AUTOCOMMIT")


@pytest.mark.migration
def test_migrations_match_models():
    admin = _admin_engine()
    # Unique name so a leftover from a crashed run can't cause a false pass.
    db_name = f"{MIG_DB}_{int(time.time())}"
    prev_url = os.environ.get("NEWS_DATABASE_URL")
    try:
        with admin.connect() as c:
            c.execute(text(f'CREATE DATABASE "{db_name}"'))
    except Exception as e:  # noqa: BLE001 - infra limitation, not a code failure
        pytest.skip(
            f"Cannot create database for migration drift check ({e}); "
            f"grant CREATEDB to the test role to enable it."
        )

    mig_url = admin.url.set(database=db_name)
    # alembic/env.py resolves the URL from NEWS_DATABASE_URL, so point it at the
    # throwaway database for the duration of the migration run. Use the unmasked
    # string form — str() masks the password as "***" and would break auth.
    mig_url_str = mig_url.render_as_string(hide_password=False)
    os.environ["NEWS_DATABASE_URL"] = mig_url_str
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", mig_url_str)
    insp_engine = None
    try:
        command.upgrade(cfg, "head")
        insp_engine = create_engine(mig_url)
        insp = inspect(insp_engine)
        migrated = set(insp.get_table_names())
        modeled = set(Base.metadata.tables.keys())
        missing_tables = modeled - migrated
        assert not missing_tables, f"Model tables missing from migrations: {missing_tables}"

        for table in sorted(modeled):
            cols = {c["name"] for c in insp.get_columns(table)}
            model_cols = set(Base.metadata.tables[table].columns.keys())
            missing_cols = model_cols - cols
            assert not missing_cols, (
                f"Columns missing in migrated table {table}: {missing_cols}"
            )
    finally:
        os.environ["NEWS_DATABASE_URL"] = prev_url or ""
        if insp_engine is not None:
            insp_engine.dispose()
        with admin.connect() as c:
            c.execute(
                text(
                    f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname='{db_name}' AND pid <> pg_backend_pid()"
                )
            )
            c.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
