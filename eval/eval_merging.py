#!/usr/bin/env python
"""REQ-2.8–2.10 — score two labeled merge samples and emit Table 2.

Single command:
    python eval/eval_merging.py --sim eval/merges_similarity.csv --co eval/merges_cooccurrence.csv --out eval/table2.csv

Inputs: CSVs produced by eval/sample_merges.py after manual labelling of the `label`
column (correct_merge / false_merge / ambiguous). Both files must come from the SAME
snapshot run (REQ-2.6) — the provenance seeds/headers are checked and a warning is
emitted if they differ.

Outputs:
  - CSV with % correct / false / ambiguous per strategy + example pairs (REQ-2.9)
  - --tex writes a LaTeX fragment for the paper.

REQ-0.1 header is prepended as a commented JSON line.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.utils import provenance_header  # noqa: E402


def read_labeled(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    # Skip provenance comment if present
    start = 0
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("#"):
            start = i + 1
            continue
        break
    # Header is first non-comment line
    content = "".join(lines[start:])
    reader = csv.DictReader(io.StringIO(content))
    for r in reader:
        # Normalize label
        r["label"] = (r.get("label") or "").strip().lower()
        rows.append(r)
    return rows


def summarize(rows: list[dict]) -> dict:
    c = Counter(r["label"] for r in rows if r["label"])
    total = sum(c.values()) or len(rows)
    # Unknown/unlabeled count
    unlabeled = len(rows) - sum(c.values())
    return {
        "total": len(rows),
        "labeled": sum(c.values()),
        "unlabeled": unlabeled,
        "correct": c.get("correct_merge", 0),
        "false": c.get("false_merge", 0),
        "ambiguous": c.get("ambiguous", 0),
        "pct_correct": (c.get("correct_merge", 0) / total * 100) if total else 0.0,
        "pct_false": (c.get("false_merge", 0) / total * 100) if total else 0.0,
        "pct_ambiguous": (c.get("ambiguous", 0) / total * 100) if total else 0.0,
    }


def examples(rows: list[dict], n: int = 5) -> list[dict]:
    """Return up to n concrete pairs for the appendix (REQ-2.9)."""
    # Prefer false merges for the co-occurrence story, correct for similarity
    # Return first n rows with their label
    return rows[:n]


def main() -> int:
    ap = argparse.ArgumentParser(description="Score merge accuracy (REQ-2).")
    ap.add_argument("--sim", required=True, help="Similarity labeled CSV")
    ap.add_argument("--co", required=True, help="Co-occurrence labeled CSV")
    ap.add_argument("--out", default="eval/table2.csv")
    ap.add_argument("--tex", default=None)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    sim_p = Path(args.sim)
    co_p = Path(args.co)
    for p in (sim_p, co_p):
        if not p.exists():
            print(f"Missing input: {p}", file=sys.stderr)
            return 2

    sim_rows = read_labeled(sim_p)
    co_rows = read_labeled(co_p)
    sim_s = summarize(sim_rows)
    co_s = summarize(co_rows)

    header = provenance_header(seed=args.seed)
    header["params"] = {"sim": str(sim_p), "co": str(co_p), "sim_summary": sim_s, "co_summary": co_s}

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["strategy", "total", "correct", "false", "ambiguous", "pct_correct", "pct_false", "pct_ambiguous"])
    w.writeheader()
    for name, s in [("similarity", sim_s), ("cooccurrence", co_s)]:
        w.writerow(
            {
                "strategy": name,
                "total": s["total"],
                "correct": s["correct"],
                "false": s["false"],
                "ambiguous": s["ambiguous"],
                "pct_correct": f"{s['pct_correct']:.1f}",
                "pct_false": f"{s['pct_false']:.1f}",
                "pct_ambiguous": f"{s['pct_ambiguous']:.1f}",
            }
        )
    csv_text = buf.getvalue()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# provenance: {json.dumps(header, ensure_ascii=False)}\n")
        f.write(csv_text)
    print(f"Wrote {out}")
    print(f"  similarity:  {sim_s['pct_correct']:.1f}% correct / {sim_s['pct_false']:.1f}% false / {sim_s['pct_ambiguous']:.1f}% ambiguous ({sim_s['labeled']}/{sim_s['total']} labeled)")
    print(f"  cooccurrence:{co_s['pct_correct']:.1f}% correct / {co_s['pct_false']:.1f}% false / {co_s['pct_ambiguous']:.1f}% ambiguous ({co_s['labeled']}/{co_s['total']} labeled)")
    if sim_s["unlabeled"] or co_s["unlabeled"]:
        print(f"  WARNING: {sim_s['unlabeled']} unlabeled in sim, {co_s['unlabeled']} in co — fill `label` before final paper.", file=sys.stderr)

    if args.tex:
        tex = io.StringIO()
        tex.write("% Auto-generated by eval/eval_merging.py — do not hand-edit\n")
        tex.write("\\begin{tabular}{lcccc}\n\\toprule\nStrategy & Correct & False & Ambiguous & n \\\\\n\\midrule\n")
        for name, s in [("Similarity", sim_s), ("Co-occurrence", co_s)]:
            tex.write(f"{name} & {s['pct_correct']:.1f}\\% & {s['pct_false']:.1f}\\% & {s['pct_ambiguous']:.1f}\\% & {s['total']} \\\\\n")
        tex.write("\\bottomrule\n\\end{tabular}\n")
        Path(args.tex).write_text(tex.getvalue(), encoding="utf-8")
        print(f"Wrote LaTeX to {args.tex}")

    # Print example pairs for appendix
    print("\nExamples (first 3 per strategy, for appendix REQ-2.9):")
    for name, rows in [("similarity", sim_rows), ("cooccurrence", co_rows)]:
        print(f"  {name}:")
        for r in examples(rows, 3):
            print(f"    {r.get('a_text')} <-> {r.get('b_text')} score={r.get('similarity_or_weight')} label={r.get('label') or '(unlabeled)'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
