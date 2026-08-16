"""Backfill story clusters for already-analyzed articles (one-off after deploy)."""

from src.nlp.stories import backfill_stories

if __name__ == "__main__":
    n = backfill_stories()
    print(f"Clustered {n} articles into stories.")
