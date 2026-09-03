#!/usr/bin/env python
"""REQ-1.10–1.11 — run the pinned ner image against articles.jsonl and emit predictions.

Single command:
    python eval/run_ner.py --in eval/articles.jsonl --out eval/predictions.jsonl

Isolates model behavior: calls src.nlp.ner.extract_entities directly on stored text
(REQ-1.11), so pipeline side-effects are not involved. Uses the same Docker image
only in the sense that the code path is identical — pin the image tag in REQ-0.1
header and run this script inside that image for strict parity:

    docker compose run --rm worker python eval/run_ner.py --in eval/articles.jsonl --out eval/predictions.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.utils import provenance_header, write_jsonl_with_header  # noqa: E402


def load_articles(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if "_provenance" in obj:
                continue
            rows.append(obj)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Run NER model over sampled articles (REQ-1.10).")
    ap.add_argument("--in", dest="inp", default="eval/articles.jsonl")
    ap.add_argument("--out", default="eval/predictions.jsonl")
    ap.add_argument("--threshold", type=float, default=0.3, help="GLiNER threshold")
    ap.add_argument("--labels", nargs="*", default=None, help="Override label list")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    inp = Path(args.inp)
    if not inp.exists():
        print(f"Input not found: {inp}. Run eval/sample_articles.py first.", file=sys.stderr)
        return 2

    rows = load_articles(inp)
    print(f"Loaded {len(rows)} articles from {inp}")

    # Defer heavy import so --help works even without ML deps
    try:
        from src.nlp.ner import DEFAULT_LABELS, extract_entities  # noqa: WPS433

        labels = args.labels or DEFAULT_LABELS
        print(f"Using labels={labels} threshold={args.threshold}")
    except Exception as e:
        print(f"NER import failed ({e}); emitting empty predictions.", file=sys.stderr)
        labels = args.labels or ["person", "organization", "location"]

        def extract_entities(text, labels=None, threshold=0.3):  # type: ignore[no-redef]
            return []

    header = provenance_header(seed=args.seed)
    header["params"] = {"threshold": args.threshold, "labels": labels, "input": str(inp)}

    out_rows: list[dict] = []
    for r in rows:
        text = r.get("text") or ""
        preds = extract_entities(text, labels=labels, threshold=args.threshold)
        # Normalize prediction schema to REQ-1.9
        ents = []
        for p in preds:
            # GLiNER returns {text, label, start, end, confidence}
            ents.append(
                {
                    "start": int(p.get("start", 0)),
                    "end": int(p.get("end", 0)),
                    "type": p.get("label", p.get("type", "MISC")),
                    "text": p.get("text", text[p.get("start", 0) : p.get("end", 0)]),
                    "confidence": p.get("confidence"),
                }
            )
        out_rows.append({**r, "entities": ents})

    write_jsonl_with_header(Path(args.out), header, out_rows)
    print(f"Wrote {len(out_rows)} prediction rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
