"""Seed sources from config/sources.yml into the database."""


import yaml
from sqlalchemy import select

from config.settings import settings
from src.db.models.source import Source
from src.db.session import SessionLocal


def seed() -> int:
    sources_file = settings.config_dir / "sources.yml"
    if not sources_file.exists():
        print(f"Sources file not found: {sources_file}")
        return 0

    with open(sources_file) as f:
        data = yaml.safe_load(f)

    entries = data.get("sources", [])
    if not entries:
        print("No sources defined in sources.yml")
        return 0

    added = 0
    with SessionLocal() as session:
        for entry in entries:
            exists = session.execute(
                select(Source).where(Source.url == entry["url"])
            ).scalar()
            if exists:
                continue

            source = Source(
                name=entry["name"],
                url=entry["url"],
                rss_url=entry.get("rss"),
                enabled=entry.get("enabled", True),
            )
            session.add(source)
            added += 1

        session.commit()

    print(f"Seeded {added} new sources ({len(entries)} total in config)")
    return added


if __name__ == "__main__":
    seed()
