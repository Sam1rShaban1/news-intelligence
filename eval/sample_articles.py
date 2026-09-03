#!/usr/bin/env python
"""Sample 200 articles for REQ-1.1–1.4 — stratified by source, seeded.

Single command:
    python eval/sample_articles.py --out eval/articles.jsonl

Reads from the live Postgres (NEWS_DATABASE_URL) in status=analyzed. Falls back to
a reproducible synthetic stub (so CI/docs still work when the DB is down).

REQ-0.1 header is written as the first JSONL line; REQ-0.4 seed is fixed (default 42).
REQ-1.2: no more than 40% of a language's 50-article sample from one outlet.
"""

from __future__ import annotations

import argparse
import collections
import os
import sys
from pathlib import Path

# Ensure repo root on sys.path so `config.settings` and `eval.utils` import cleanly
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.utils import ensure_seed, provenance_header, write_jsonl_with_header  # noqa: E402

DEFAULT_SEED = 42
LANGUAGES = ["mk", "sq", "en", "tr"]
PER_LANG = 50
MAX_SHARE = 0.40  # REQ-1.2


def synthetic_rows() -> list[dict]:
    out: list[dict] = []
    for lang in LANGUAGES:
        for i in range(PER_LANG):
            out.append(
                {
                    "article_id": f"synthetic-{lang}-{i:03d}",
                    "language": lang,
                    "source": f"synthetic-source-{i % 4}",
                    "title": f"Synthetic {lang} article {i}",
                    "text": f"This is synthetic content for {lang} article {i}. Skopje Tirana Berlin. Person: Example {i}.",
                    "published_at": "2026-01-01T00:00:00Z",
                }
            )
    return out


def sample_from_db(seed: int, per_lang: int, max_share: float) -> list[dict]:
    try:
        from sqlalchemy import select

        from config.settings import settings
        from src.db.models.article import Article
        from src.db.models.source import Source
        from src.db.session import SessionLocal
    except Exception as e:
        print(f"[sample_articles] DB import failed ({e}); using synthetic stub.", file=sys.stderr)
        return synthetic_rows()

    ensure_seed(seed)
    # We do stratified sampling in Python so the cap logic is auditable.
    import random

    db_url = getattr(settings, "database_url", None)
    # Quick connectivity probe; fall back to synthetic if DB is unreachable
    try:
        with SessionLocal() as s:
            s.execute(select(Source.id).limit(1))
    except Exception as e:
        print(f"[sample_articles] DB unreachable ({e}); using synthetic stub.", file=sys.stderr)
        return synthetic_rows()

    rows: list[dict] = []
    with SessionLocal() as session:
        for lang in LANGUAGES:
            # Pull all analyzed articles for this language
            q = (
                select(Article, Source.name)
                .join(Source, Source.id == Article.source_id)
                .where(Article.status == "analyzed", Article.language == lang)
            )
            recs = session.execute(q).all()
            if not recs:
                print(f"[sample_articles] No analyzed articles for {lang}; synthesizing that slice.", file=sys.stderr)
                for i in range(per_lang):
                    rows.append(
                        {
                            "article_id": f"synthetic-{lang}-{i:03d}",
                            "language": lang,
                            "source": f"synthetic-source-{i % 4}",
                            "title": f"Synthetic {lang} article {i}",
                            "text": f"Synthetic {lang} article {i} content.",
                            "published_at": None,
                        }
                    )
                continue

            # Group by source
            by_source: dict[str, list] = collections.defaultdict(list)
            for art, src_name in recs:
                by_source[src_name or "unknown"].append(art)

            # Randomized, capped selection
            random.shuffle(recs)
            # Greedy capped pick: keep per-source counters
            picked: list = []
            counts: collections.Counter = collections.Counter()
            cap = max(1, int(per_lang * max_share))
            for art, src_name in recs:
                if len(picked) >= per_lang:
                    break
                key = src_name or "unknown"
                if counts[key] >= cap:
                    continue
                picked.append((art, key))
                counts[key] += 1

            # If capped selection undershot (skewed feed distribution), fill remaining
            # from the pool ignoring the cap but still document the imbalance per REQ-1.1.
            if len(picked) < per_lang:
                print(
                    f"[sample_articles] {lang}: capped pick only {len(picked)}/{per_lang}; "
                    f"backfilling beyond cap to reach minimum. Imbalance must be documented in the paper.",
                    file=sys.stderr,
                )
                for art, src_name in recs:
                    if len(picked) >= per_lang:
                        break
                    if any(p[0].id == art.id for p in picked):
                        continue
                    picked.append((art, src_name or "unknown"))

            # Trim or pad to exactly per_lang
            picked = picked[:per_lang]
            if len(picked) < per_lang:
                print(
                    f"[sample_articles] {lang}: only {len(picked)} analyzable rows available (<{per_lang}). "
                    f"REVIEW: backfill from archived feeds or document shortfall.",
                    file=sys.stderr,
                )

            for art, src_name in picked:
                rows.append(
                    {
                        "article_id": str(art.id),
                        "language": art.language,
                        "source": src_name,
                        "title": art.title or "",
                        "text": (art.content or art.summary or art.title or ""),
                        "published_at": art.published_date.isoformat() if art.published_date else None,
                    }
                )

    # Final shuffle so languages are interleaved reproducibly
    import random as _r

    _r.seed(seed)
    _r.shuffle(rows)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Sample 200 articles stratified by source (REQ-1).")
    ap.add_argument("--out", default="eval/articles.jsonl", help="Output JSONL path")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="REQ-0.4 fixed seed")
    ap.add_argument("--per-lang", type=int, default=PER_LANG)
    ap.add_argument("--max-share", type=float, default=MAX_SHARE)
    args = ap.parse_args()

    rows = sample_from_db(args.seed, args.per_lang, args.max_share)
    header = provenance_header(seed=args.seed)
    # Record sampling params in header for auditability
    header["params"] = {"per_lang": args.per_lang, "max_share": args.max_share, "languages": LANGUAGES}
    out = Path(args.out)
    write_jsonl_with_header(out, header, rows)
    print(f"Wrote {len(rows)} articles to {out} (seed={args.seed}). Header commit={header['git_commit'][:8]}")
    # Language breakdown
    cnt = collections.Counter(r["language"] for r in rows)
    for lang in LANGUAGES:
        print(f"  {lang}: {cnt.get(lang, 0)}")
    # Source cap audit
    by_lang_source: dict[str, collections.Counter] = {l: collections.Counter() for l in LANGUAGES}
    for r in rows:
        by_lang_source[r["language"]][r["source"]] += 1
    for lang in LANGUAGES:
        top = by_lang_source[lang].most_common(1)
        if top:
            share = top[0][1] / max(1, cnt[lang])
            flag = " OK" if share <= args.max_share + 1e-9 else " EXCEEDS CAP"
            print(f"  {lang} top-source share: {share:.1%} ({top[0][0]}){flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
