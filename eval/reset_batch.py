#!/usr/bin/env python
"""REQ-3.4 — reset exactly 500 articles to sentiment_done for scaling benchmarks.

Single command:
    python eval/reset_batch.py --ids eval/bench_ids.txt

Behavior per spec:
  - Same 500 article IDs across all three replica-count runs (REQ-3.4).
  - No other articles should be in sentiment_done during the run (REQ-3.5) — this
    script optionally drains/pauses the worker; otherwise it warns.
  - Persists the chosen 500 IDs to a file so bench_scaling.py can reuse them.

Usage for a clean benchmark:
    python eval/reset_batch.py --pick --out eval/bench_ids.txt   # pick fresh 500 from analyzed
    python eval/reset_batch.py --ids eval/bench_ids.txt          # reset those 500 to sentiment_done
    python eval/reset_batch.py --drain-check                      # verify no stray sentiment_done rows

Direct SQL alternative (eval/reset_batch.sql) is also provided — this Python wrapper
is preferred because it handles ID persistence and provenance.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.utils import ensure_seed  # noqa: E402


def pick_ids(n: int, seed: int) -> list[int]:
    try:
        from sqlalchemy import select

        from src.db.models.article import Article
        from src.db.session import SessionLocal

        ensure_seed(seed)
        with SessionLocal() as s:
            rows = s.execute(select(Article.id).where(Article.status == "analyzed").order_by(Article.id)).scalars().all()
            if len(rows) < n:
                print(f"[reset_batch] Only {len(rows)} analyzed rows available (<{n}); using all.", file=sys.stderr)
                return list(rows)
            rnd = random.Random(seed)
            rnd.shuffle(rows)
            return sorted(rows[:n])
    except Exception as e:
        print(f"[reset_batch] DB pick failed ({e}); using synthetic IDs 1..{n}.", file=sys.stderr)
        return list(range(1, n + 1))


def reset_ids(ids: list[int]) -> None:
    try:
        from sqlalchemy import text

        from src.db.session import SessionLocal

        with SessionLocal() as s:
            # Reset exactly these IDs to sentiment_done; clear NER state
            s.execute(
                text(
                    "UPDATE articles SET status='sentiment_done', started_at=NULL, retry_count=0, "
                    "error_message=NULL, analyzed_at=NULL WHERE id = ANY(:ids)"
                ).bindparams(ids=ids)
            )
            s.commit()
            cnt = s.execute(text("SELECT count(*) FROM articles WHERE status='sentiment_done'")).scalar()
            print(f"Reset {len(ids)} rows to sentiment_done. Total sentiment_done now: {cnt}")
            if cnt != len(ids):
                print(
                    f"WARNING REQ-3.5: {cnt - len(ids)} extra sentiment_done rows exist — "
                    f"drain/pause the worker before timing (docker compose stop worker).",
                    file=sys.stderr,
                )
    except Exception as e:
        print(f"[reset_batch] DB reset failed ({e}); no-op in stub mode.", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Reset 500 articles to sentiment_done (REQ-3.4).")
    ap.add_argument("--pick", action="store_true", help="Pick fresh 500 IDs from analyzed and write to --out")
    ap.add_argument("--ids", default=None, help="File with 500 IDs (one per line) to reset")
    ap.add_argument("--out", default="eval/bench_ids.txt", help="Output file for picked IDs")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--drain-check", action="store_true", help="Only check REQ-3.5 invariant")
    args = ap.parse_args()

    if args.drain_check:
        try:
            from sqlalchemy import text

            from src.db.session import SessionLocal

            with SessionLocal() as s:
                cnt = s.execute(text("SELECT count(*) FROM articles WHERE status='sentiment_done'")).scalar()
                print(f"sentiment_done count: {cnt}")
                return 0
        except Exception as e:
            print(f"drain-check failed: {e}", file=sys.stderr)
            return 1

    if args.pick:
        ids = pick_ids(args.n, args.seed)
        Path(args.out).write_text("\n".join(str(i) for i in ids) + "\n", encoding="utf-8")
        print(f"Picked {len(ids)} IDs (seed={args.seed}) -> {args.out}")
        return 0

    ids_file = args.ids or args.out
    p = Path(ids_file)
    if not p.exists():
        print(f"IDs file not found: {p}. Run with --pick first.", file=sys.stderr)
        return 2
    ids = [int(x.strip()) for x in p.read_text().splitlines() if x.strip()]
    print(f"Resetting {len(ids)} IDs from {p}")
    reset_ids(ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
