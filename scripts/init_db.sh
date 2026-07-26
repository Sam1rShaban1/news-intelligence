#!/usr/bin/env bash
# First-time database initialization
set -euo pipefail

echo "Waiting for PostgreSQL to be ready..."
until docker compose exec -T postgres pg_isready -U news -d news_intelligence 2>/dev/null; do
    sleep 2
done
echo "PostgreSQL is ready."

echo "Running migrations..."
docker compose run --rm -e NEWS_DATABASE_URL=postgresql://news:news@postgres:5432/news_intelligence \
    worker -m alembic upgrade head

echo "Seeding sources..."
docker compose run --rm -e NEWS_DATABASE_URL=postgresql://news:news@postgres:5432/news_intelligence \
    -e PYTHONPATH=/app worker scripts/seed_sources.py

echo "Database initialized successfully."
