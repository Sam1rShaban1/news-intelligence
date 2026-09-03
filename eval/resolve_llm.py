#!/usr/bin/env python
"""Resolve LLM surface-form annotations to exact Label Studio spans.

Reads eval/llm_batch*.txt lines: TASK <id> || <surface> || <TYPE>
- Finds ALL occurrences (case-sensitive) in the task text from Label Studio DB.
- Overlap resolution: longest-first greedy (e.g. 'Donald Trump' beats 'Trump').
- Reports unmatched surfaces for the annotator to fix.
- Writes eval/llm_resolved.json: {task_id: [LS result dicts]} (read-only DB use).

Usage: python3 eval/resolve_llm.py [--check-only]
"""

import glob
import json
import random
import sqlite3
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "eval" / "label_studio.sqlite3"
VALID = {"PERSON", "ORG", "LOCATION"}


def rid(n=8):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def load_annotations():
    anns = {}  # tid -> [(surface, type)]
    for path in sorted(glob.glob(str(ROOT / "eval" / "llm_batch*.txt"))):
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                parts = [p.strip() for p in ln.split("||")]
                if len(parts) != 3 or not parts[0].upper().startswith("TASK"):
                    print(f"BAD LINE in {path}: {ln[:100]}", file=sys.stderr)
                    continue
                try:
                    tid = int(parts[0].split()[1])
                except Exception:
                    print(f"BAD TASK ID in {path}: {ln[:100]}", file=sys.stderr)
                    continue
                anns.setdefault(tid, []).append((parts[1], parts[2].upper()))
    return anns


def main():
    check_only = "--check-only" in sys.argv
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    tasks = {r[0]: json.loads(r[1]) for r in cur.execute("SELECT id, data FROM task").fetchall()}

    anns = load_annotations()
    resolved, unmatched, badtype = {}, [], []
    total_spans = 0
    for tid, items in sorted(anns.items()):
        if tid not in tasks:
            print(f"UNKNOWN TASK {tid}", file=sys.stderr)
            continue
        text = tasks[tid].get("text", "")
        cands = []  # (start, end, -len, type, surface)
        for surface, typ in items:
            if typ not in VALID:
                badtype.append((tid, surface, typ))
                continue
            idx, found = 0, False
            while True:
                i = text.find(surface, idx)
                if i < 0:
                    break
                found = True
                cands.append((i, i + len(surface), -len(surface), typ, surface))
                idx = i + 1
            if not found:
                unmatched.append((tid, surface, typ))
        # longest-first greedy dedup
        cands.sort(key=lambda c: (c[0], c[2]))
        kept, taken = [], []
        for s, e, _, typ, surface in cands:
            if any(s < te and e > ts for ts, te in taken):
                continue
            taken.append((s, e))
            kept.append({
                "value": {"start": s, "end": e, "text": text[s:e], "labels": [typ]},
                "id": rid(), "from_name": "label", "to_name": "text",
                "type": "labels", "origin": "prediction",
            })
        resolved[str(tid)] = kept
        total_spans += len(kept)

    print(f"tasks annotated: {len(anns)}  spans: {total_spans}")
    print(f"unmatched surfaces: {len(unmatched)}")
    for tid, surface, typ in unmatched:
        print(f"  UNMATCHED task={tid} type={typ} surface={surface[:80]!r}")
    print(f"bad types: {len(badtype)}")
    for tid, surface, typ in badtype:
        print(f"  BADTYPE task={tid} type={typ} surface={surface[:80]!r}")

    if not check_only:
        out = ROOT / "eval" / "llm_resolved.json"
        out.write_text(json.dumps(resolved, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {out}")
    return 0 if not unmatched and not badtype else 1


if __name__ == "__main__":
    raise SystemExit(main())
