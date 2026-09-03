#!/usr/bin/env python
"""REQ-1.12–1.14 — score gold vs predictions and emit Table 1.

Single command:
    python eval/eval_ner.py --gold eval/gold.jsonl --pred eval/predictions.jsonl --out eval/table1.csv

Match modes:
  - strict: exact span [start,end) and type must match (REQ-1.12 primary)
  - relaxed: IoU > 0.5 and type matches — reported when --relaxed is set

Outputs:
  - CSV with per-language and per-type P/R/F1 plus macro average
  - --tex flag also writes a LaTeX fragment for main.tex (avoids hand-typed tables, REQ-1.6 acceptance)

Header (REQ-0.1) is written as the first commented line of the CSV.
Gold and prediction files are JSONL with first line = provenance header.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.utils import provenance_header, write_csv_with_header  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
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


def span_iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    s = max(a[0], b[0])
    e = min(a[1], b[1])
    inter = max(0, e - s)
    if inter == 0:
        return 0.0
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union else 0.0


def score_for_rows(gold_rows: list[dict], pred_rows: list[dict], relaxed: bool = False) -> dict:
    """Return per-(lang,type) and aggregate P/R/F1.

    Matching: exact span+type (strict) or IoU>0.5+type (relaxed). Each gold span
    matches at most one predicted span (greedy by overlap / exact first).
    """
    # Index predictions by article_id
    pred_by_id = {str(r.get("article_id")): r for r in pred_rows}
    langs = sorted({r.get("language", "unknown") for r in gold_rows})
    types = ["PERSON", "PER", "ORG", "LOCATION", "LOC"]
    # Normalize type keys: map PER/PERSON -> PERSON, LOC/LOCATION -> LOCATION
    def norm_type(t: str) -> str:
        u = (t or "").upper()
        if u in ("PER", "PERSON"):
            return "PERSON"
        if u in ("LOC", "LOCATION"):
            return "LOCATION"
        if u == "ORG":
            return "ORG"
        return u

    # Counters: key = (lang, type) -> [tp, fp, fn]
    per: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    per_type: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    overall = [0, 0, 0]

    for g in gold_rows:
        aid = str(g.get("article_id"))
        lang = g.get("language", "unknown")
        gold_ents = g.get("entities") or []
        pred_ents = (pred_by_id.get(aid, {}).get("entities") or []) if aid in pred_by_id else []

        # Build normalized lists: (start,end,type)
        g_spans = [(int(e["start"]), int(e["end"]), norm_type(e.get("type", e.get("label", "")))) for e in gold_ents if "start" in e and "end" in e]
        p_spans = [(int(e["start"]), int(e["end"]), norm_type(e.get("type", e.get("label", "")))) for e in pred_ents if "start" in e and "end" in e]

        matched_g = set()
        matched_p = set()
        if not relaxed:
            # Exact matching via set lookup
            g_set_to_idx = {(s, e, t): i for i, (s, e, t) in enumerate(g_spans)}
            p_set_to_idx = {(s, e, t): i for i, (s, e, t) in enumerate(p_spans)}
            common = set(g_set_to_idx) & set(p_set_to_idx)
            for key in common:
                gi = g_set_to_idx[key]
                pi = p_set_to_idx[key]
                matched_g.add(gi)
                matched_p.add(pi)
                t = key[2]
                per[(lang, t)][0] += 1
                per_type[t][0] += 1
                overall[0] += 1
            # FP = predicted not matched; FN = gold not matched
            for i, (_, _, t) in enumerate(p_spans):
                if i not in matched_p:
                    per[(lang, t)][1] += 1
                    per_type[t][1] += 1
                    overall[1] += 1
            for i, (_, _, t) in enumerate(g_spans):
                if i not in matched_g:
                    per[(lang, t)][2] += 1
                    per_type[t][2] += 1
                    overall[2] += 1
        else:
            # Relaxed: greedy IoU>0.5 + type match; consume first match per gold span
            g_unmatched = set(range(len(g_spans)))
            p_unmatched = set(range(len(p_spans)))
            for gi in list(g_unmatched):
                gs, ge, gt = g_spans[gi]
                best = None
                best_iou = 0.0
                for pi in list(p_unmatched):
                    ps, pe, pt = p_spans[pi]
                    if pt != gt:
                        continue
                    iou = span_iou((gs, ge), (ps, pe))
                    if iou > 0.5 and iou > best_iou:
                        best, best_iou = pi, iou
                if best is not None:
                    g_unmatched.remove(gi)
                    p_unmatched.remove(best)
                    per[(lang, gt)][0] += 1
                    per_type[gt][0] += 1
                    overall[0] += 1
            for pi in p_unmatched:
                _, _, t = p_spans[pi]
                per[(lang, t)][1] += 1
                per_type[t][1] += 1
                overall[1] += 1
            for gi in g_unmatched:
                _, _, t = g_spans[gi]
                per[(lang, t)][2] += 1
                per_type[t][2] += 1
                overall[2] += 1

    def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
        return p, r, f1

    # Build table rows
    rows_out: list[dict] = []
    langs_sorted = sorted({k[0] for k in per} | {r.get("language", "unknown") for r in gold_rows})
    types_sorted = sorted({k[1] for k in per} | set(per_type))
    for lang in langs_sorted:
        for t in types_sorted:
            tp, fp, fn = per.get((lang, t), [0, 0, 0])
            if tp == 0 and fp == 0 and fn == 0:
                continue
            p, r, f1 = prf(tp, fp, fn)
            rows_out.append({"language": lang, "type": t, "tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1})

    # Per-type aggregate
    for t in sorted(per_type):
        tp, fp, fn = per_type[t]
        p, r, f1 = prf(tp, fp, fn)
        rows_out.append({"language": "ALL", "type": t, "tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1})

    # Overall micro
    tp, fp, fn = overall
    p, r, f1 = prf(tp, fp, fn)
    rows_out.append({"language": "ALL", "type": "ALL", "tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1})

    # Macro across languages (mean of per-language F1s for the ALL-type)
    # Recompute macro cleanly: mean of each language's overall F1
    macro_f1s: list[float] = []
    for lang in langs_sorted:
        # aggregate that lang across types
        tp_l = sum(per.get((lang, t), [0, 0, 0])[0] for t in types_sorted)
        fp_l = sum(per.get((lang, t), [0, 0, 0])[1] for t in types_sorted)
        fn_l = sum(per.get((lang, t), [0, 0, 0])[2] for t in types_sorted)
        _, _, f1_l = prf(tp_l, fp_l, fn_l)
        if tp_l or fp_l or fn_l:
            macro_f1s.append(f1_l)
    macro = sum(macro_f1s) / len(macro_f1s) if macro_f1s else 0.0

    return {"rows": rows_out, "macro_f1": macro, "overall": {"tp": tp, "fp": fp, "fn": fn, "p": p, "r": r, "f1": f1}}


def main() -> int:
    ap = argparse.ArgumentParser(description="Score NER predictions (REQ-1).")
    ap.add_argument("--gold", default="eval/gold.jsonl", help="Gold JSONL (REQ-1.9)")
    ap.add_argument("--pred", default="eval/predictions.jsonl", help="Predictions JSONL")
    ap.add_argument("--out", default="eval/table1.csv", help="Output CSV")
    ap.add_argument("--tex", default=None, help="Also write LaTeX fragment to this path")
    ap.add_argument("--relaxed", action="store_true", help="Use IoU>0.5 relaxed matching")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    gold_p = Path(args.gold)
    pred_p = Path(args.pred)
    if not gold_p.exists():
        print(f"Gold file not found: {gold_p}", file=sys.stderr)
        return 2
    if not pred_p.exists():
        print(f"Predictions file not found: {pred_p}", file=sys.stderr)
        return 2

    gold = load_jsonl(gold_p)
    pred = load_jsonl(pred_p)
    mode = "relaxed" if args.relaxed else "strict"
    result = score_for_rows(gold, pred, relaxed=args.relaxed)

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["language", "type", "tp", "fp", "fn", "precision", "recall", "f1"])
    w.writeheader()
    for r in result["rows"]:
        w.writerow({**r, "precision": f"{r['precision']:.4f}", "recall": f"{r['recall']:.4f}", "f1": f"{r['f1']:.4f}"})
    # Append macro comment as a trailing row (so it's in the CSV but easy to filter)
    w.writerow({"language": "# macro_f1", "type": mode, "tp": "", "fp": "", "fn": "", "precision": "", "recall": "", "f1": f"{result['macro_f1']:.4f}"})
    csv_text = buf.getvalue()

    header = provenance_header(seed=args.seed)
    header["params"] = {"mode": mode, "gold": str(gold_p), "pred": str(pred_p)}
    write_csv_with_header(Path(args.out), header, csv_text)
    print(f"Wrote {args.out} ({len(result['rows'])} rows, mode={mode}, macro_f1={result['macro_f1']:.4f})")
    print(f"Overall micro P={result['overall']['p']:.4f} R={result['overall']['r']:.4f} F1={result['overall']['f1']:.4f}")

    if args.tex:
        tex = io.StringIO()
        tex.write("% Auto-generated by eval/eval_ner.py — do not hand-edit. Mode: " + mode + "\n")
        tex.write("\\begin{tabular}{lllccc}\n\\toprule\nLanguage & Type & P & R & F1 \\\\\n\\midrule\n")
        for r in result["rows"]:
            if r["language"] == "ALL" and r["type"] == "ALL":
                continue
            tex.write(f"{r['language']} & {r['type']} & {r['precision']:.3f} & {r['recall']:.3f} & {r['f1']:.3f} \\\\\n")
        o = result["overall"]
        tex.write("\\midrule\n")
        tex.write(f"\\multicolumn{{2}}{{l}}{{Overall (micro)}} & {o['p']:.3f} & {o['r']:.3f} & {o['f1']:.3f} \\\\\n")
        tex.write(f"\\multicolumn{{2}}{{l}}{{Macro F1}} & & & {result['macro_f1']:.3f} \\\\\n")
        tex.write("\\bottomrule\n\\end{tabular}\n")
        Path(args.tex).write_text(tex.getvalue(), encoding="utf-8")
        print(f"Wrote LaTeX fragment to {args.tex}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
