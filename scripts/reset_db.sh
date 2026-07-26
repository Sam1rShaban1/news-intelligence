#!/usr/bin/env bash
# Reset the database — drop and recreate all tables, then seed
set -euo pipefail

echo "Dropping and recreating database schema..."
docker compose exec -T postgres psql -U news -d news_intelligence -c "
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO news;
"

echo "Running migrations..."
docker compose run --rm -e NEWS_DATABASE_URL=postgresql://news:news@postgres:5432/news_intelligence \
    worker -m alembic upgrade head

echo "Seeding sources..."
docker compose run --rm -e NEWS_DATABASE_URL=postgresql://news:news@postgres:5432/news_intelligence \
    worker python scripts/seed_sources.py

echo "Done."
