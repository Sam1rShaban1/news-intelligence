#!/usr/bin/env python
"""REQ-4 — search latency: p50/p95 same-script vs cross-script (table for Section 4.4).

Single command:
    python eval/bench_search.py --same eval/queries_same_script.txt --cross eval/queries_cross_script.txt --out eval/search_raw.csv

Measures the live /search endpoint (REQ-4.7) including API overhead, with a warmup
(REQ-4.8). Queries are drawn from real entity surface forms (REQ-4.5) when the DB
is reachable; otherwise synthetic Latin/Cyrillic examples are used so the script
remains runnable for CI.

Output: raw per-query CSV + summary (p50/p95 same-script, p50/p95 cross-script) per REQ-4.12.
Header (REQ-0.1) is the first commented line.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.utils import provenance_header  # noqa: E402

DEFAULT_API = "http://localhost:8000"


def load_queries(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]


def build_query_sets(same_path: Path, cross_path: Path) -> tuple[list[str], list[str]]:
    same = load_queries(same_path)
    cross = load_queries(cross_path)
    if same and cross:
        return same, cross
    # Try to build from entity_nodes when DB is available (REQ-4.5)
    try:
        from sqlalchemy import select

        from src.db.models.entity_node import EntityNode
        from src.db.session import SessionLocal
        from src.nlp.normalize import normalize_text

        same_built: list[str] = []
        cross_built: list[str] = []
        with SessionLocal() as s:
            rows = s.execute(select(EntityNode.canonical_text, EntityNode.label).limit(300)).all()
            for txt, _label in rows:
                # Heuristic: Cyrillic-containing originals are cross-script candidates
                # Our canonical_text is already normalized/latinized, so also sample from entities.text
                t = (txt or "").strip()
                if not t or len(t) < 3:
                    continue
                # Cheap script guess: contains Cyrillic codepoints?
                has_cyr = any(0x0400 <= ord(ch) <= 0x04FF for ch in t)
                if has_cyr:
                    cross_built.append(t)
                else:
                    same_built.append(t)
        # If canonical_text is already folded (no Cyrillic), fall back to splitting
        if not same_built:
            same_built = [r[0] for r in rows[:100] if r[0]]
        if not cross_built:
            # Synthetic cross-script: Macedonian Cyrillic->latin examples
            cross_built = ["Скопје", "Тирана", "Охрид", "Приштина", "Берлин"] * 20
        # Fill gaps from whichever list has items
        if not same:
            same = same_built[:100]
        if not cross:
            cross = cross_built[:100]
    except Exception as e:
        print(f"[bench_search] DB query build failed ({e}); using synthetic fallbacks.", file=sys.stderr)
        if not same:
            same = ["Skopje", "Tirana", "Berlin", "Pristina", "Ohrid"] * 20
        if not cross:
            cross = ["Скопје", "Тирана", "Охрид", "Приштина", "Берлин"] * 20

    # Ensure files exist for reproducibility (REQ-4.6)
    if not same_path.exists():
        same_path.write_text("\n".join(same[:100]) + "\n", encoding="utf-8")
        print(f"Wrote synthetic same-script queries to {same_path}")
    if not cross_path.exists():
        cross_path.write_text("\n".join(cross[:100]) + "\n", encoding="utf-8")
        print(f"Wrote synthetic cross-script queries to {cross_path}")
    return same[:100], cross[:100]


def _time_one(session, api: str, q: str, timeout: float = 15.0) -> tuple[float, int]:
    """Return (latency_ms, http_status). Uses httpx if available, else urllib."""
    t0 = time.perf_counter()
    try:
        import httpx  # type: ignore

        # Use a short-lived client if caller didn't pass one
        if session is None:
            with httpx.Client(timeout=timeout) as c:
                r = c.get(f"{api}/search", params={"q": q, "limit": 20})
                dt = (time.perf_counter() - t0) * 1000
                return dt, r.status_code
        else:
            r = session.get(f"{api}/search", params={"q": q, "limit": 20})
            dt = (time.perf_counter() - t0) * 1000
            return dt, r.status_code
    except ImportError:
        import urllib.request

        url = f"{api}/search?q={urllib.parse.quote(q)}&limit=20"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                resp.read()
                dt = (time.perf_counter() - t0) * 1000
                return dt, resp.status
        except Exception as e:
            dt = (time.perf_counter() - t0) * 1000
            # Map to 0 status on network failure
            return dt, 0
    except Exception:
        dt = (time.perf_counter() - t0) * 1000
        return dt, 0


def _percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    d0 = k - f
    return s[f] * (1 - d0) + s[c] * d0


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark search latency (REQ-4).")
    ap.add_argument("--same", default="eval/queries_same_script.txt")
    ap.add_argument("--cross", default="eval/queries_cross_script.txt")
    ap.add_argument("--out", default="eval/search_raw.csv")
    ap.add_argument("--api", default=DEFAULT_API, help="Base API URL (REQ-4.7 live search)")
    ap.add_argument("--warmup", type=int, default=5, help="Warmup queries (REQ-4.8)")
    ap.add_argument("--api-key", default=None, help="X-API-Key if auth is enabled")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--corpus-count", type=int, default=None, help="Override N for table; else auto-count articles")
    args = ap.parse_args()

    same_path = Path(args.same)
    cross_path = Path(args.cross)
    same_qs, cross_qs = build_query_sets(same_path, cross_path)
    if len(same_qs) < 50 or len(cross_qs) < 50:
        print(f"Need ≥50 per category (have same={len(same_qs)} cross={len(cross_qs)}).", file=sys.stderr)
        return 2

    # Corpus size N (REQ-4.1)
    corpus_n = args.corpus_count
    if corpus_n is None:
        try:
            from sqlalchemy import select, func

            from src.db.models.article import Article
            from src.db.session import SessionLocal

            with SessionLocal() as s:
                corpus_n = s.execute(select(func.count(Article.id))).scalar()
        except Exception:
            corpus_n = -1

    header = provenance_header(seed=args.seed)
    header["params"] = {"api": args.api, "corpus_n": corpus_n, "same_n": len(same_qs), "cross_n": len(cross_qs)}
    print(f"Corpus N={corpus_n} (REQ-4.1). Same={len(same_qs)} Cross={len(cross_qs)} queries. API={args.api}")

    # Warmup (REQ-4.8)
    try:
        import httpx  # type: ignore

        headers = {"X-API-Key": args.api_key} if args.api_key else {}
        client = httpx.Client(timeout=15, headers=headers)
    except ImportError:
        client = None
        print("httpx not available — falling back to urllib (less accurate).", file=sys.stderr)

    for q in (same_qs[: args.warmup] + cross_qs[: args.warmup])[: args.warmup]:
        _time_one(client, args.api, q)

    rows: list[dict] = []
    lat_same: list[float] = []
    lat_cross: list[float] = []

    def run_set(qs: list[str], label: str, bucket: list[float]) -> None:
        for q in qs:
            ms, status = _time_one(client, args.api, q)
            bucket.append(ms)
            rows.append({"category": label, "query": q, "latency_ms": round(ms, 2), "http_status": status})

    run_set(same_qs, "same_script", lat_same)
    run_set(cross_qs, "cross_script", lat_cross)

    if client is not None and hasattr(client, "close"):
        try:
            client.close()
        except Exception:
            pass

    def summarize(lat: list[float]) -> dict:
        return {
            "p50": round(_percentile(lat, 50), 2),
            "p95": round(_percentile(lat, 95), 2),
            "mean": round(statistics.mean(lat), 2) if lat else 0.0,
            "n": len(lat),
        }

    summ_same = summarize(lat_same)
    summ_cross = summarize(lat_cross)
    print(f"Same-script: p50={summ_same['p50']}ms p95={summ_same['p95']}ms mean={summ_same['mean']}ms (n={summ_same['n']})")
    print(f"Cross-script: p50={summ_cross['p50']}ms p95={summ_cross['p95']}ms mean={summ_cross['mean']}ms (n={summ_cross['n']})")

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["category", "query", "latency_ms", "http_status"])
    w.writeheader()
    for r in rows:
        w.writerow(r)
    csv_text = buf.getvalue()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    footer = "# summary: " + json.dumps({"corpus_n": corpus_n, "same_script": summ_same, "cross_script": summ_cross}, ensure_ascii=False) + "\n"
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# provenance: {json.dumps(header, ensure_ascii=False)}\n")
        f.write(csv_text)
        f.write(footer)
    print(f"Wrote {out} ({len(rows)} rows)")

    tex_path = out.with_name(out.stem + "_table.tex") if out.suffix == ".csv" else Path(str(out) + "_table.tex")
    tex = io.StringIO()
    tex.write("% Auto-generated by eval/bench_search.py\n")
    tex.write("\\begin{tabular}{lccc}\n\\toprule\nCategory & p50 (ms) & p95 (ms) & n \\\\\n\\midrule\n")
    tex.write(f"Same-script & {summ_same['p50']:.1f} & {summ_same['p95']:.1f} & {summ_same['n']} \\\\\n")
    tex.write(f"Cross-script & {summ_cross['p50']:.1f} & {summ_cross['p95']:.1f} & {summ_cross['n']} \\\\\n")
    tex.write("\\bottomrule\n\\end{tabular}\n")
    tex.write(f"% Corpus N={corpus_n}\n")
    tex_path.write_text(tex.getvalue(), encoding="utf-8")
    print(f"Wrote LaTeX to {tex_path}")

    # Corpus-size warning (REQ-4.6 acceptance)
    if corpus_n is not None and corpus_n != -1:
        print(f"Record N={corpus_n} in the paper text per REQ-4.1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
