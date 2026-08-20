"""Pytest fixtures for API route tests.

Requires a Postgres database. Point it at one with NEWS_DATABASE_URL; the
schema is (re)created from the models each session and dropped afterwards, so
no alembic history is needed. CI provides a Postgres service container.
"""

import os

import pytest

TEST_DB_URL = os.environ.get(
    "NEWS_DATABASE_URL", "postgresql://news:news@localhost:5432/news_intelligence_test"
)
os.environ["NEWS_DATABASE_URL"] = TEST_DB_URL

from fastapi.testclient import TestClient  # noqa: E402

from src.api.main import app  # noqa: E402
from src.db.models import Base  # noqa: E402
from src.db.session import engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(_schema) -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_tests():
    """Truncate every table after each test so tests never leak rows to each other."""
    yield
    from src.db.models import Base

    with engine.begin() as conn:
        conn.execute(
            __import__("sqlalchemy").text(
                "TRUNCATE TABLE "
                + ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
                + " RESTART IDENTITY CASCADE"
            )
        )
