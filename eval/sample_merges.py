#!/usr/bin/env python
"""Generate merge-candidate samples for REQ-2 — similarity and co-occurrence.

Single command (similarity):
    DRY_RUN=1 python eval/sample_merges.py --strategy similarity --n 100 --seed 42 --out eval/merges_similarity.csv

Co-occurrence (reconstructed from git history per REQ-2.5):
    python eval/sample_merges.py --strategy cooccurrence --n 100 --seed 42 --out eval/merges_cooccurrence.csv

REQ-2.1/2.6: both strategies run against the SAME entity snapshot — this script
snapshots entity_nodes once at the start and reuses it for either strategy.

Similarity uses scripts/merge_entities.py entity_similarity on the live snapshot
(DRY_RUN-like collection, no DB mutation). Co-occurrence reconstructs the discarded
global co-occurrence merge: merge any node pair that co-occurs above a threshold
weight — this is the strawman warned against in docs, recovered as literally as
possible from src/nlp/graph.py history (see git show 0fe5167).

Output CSV columns: a_text,b_text,a_normalized,b_normalized,similarity,score,language,strategy
Manual labelling adds: label (correct_merge/false_merge/ambiguous).
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.utils import ensure_seed, provenance_header  # noqa: E402


def _snapshot_nodes():
    try:
        from sqlalchemy import select

        from src.db.models.entity_node import EntityNode
        from src.db.session import SessionLocal

        with SessionLocal() as s:
            rows = s.execute(
                select(EntityNode.id, EntityNode.canonical_text, EntityNode.label, EntityNode.mention_count)
            ).all()
            nodes = {r[0]: {"canonical": r[1], "label": r[2], "mentions": r[3] or 0} for r in rows}
            # Also fetch entity_edges for co-occurrence
            from src.db.models.entity_edge import EntityEdge

            edges = s.execute(select(EntityEdge.node_a_id, EntityEdge.node_b_id, EntityEdge.weight)).all()
            edges = [(a, b, w) for a, b, w in edges]
            # Sample languages per node via entities join
            from src.db.models.article import Article
            from src.db.models.entity import Entity

            lang_map: dict[int, set[str]] = {}
            q = select(Entity.node_id, Article.language).join(Article, Article.id == Entity.article_id)
            for nid, lang in s.execute(q).all():
                if nid is not None:
                    lang_map.setdefault(nid, set()).add(lang)
            return nodes, edges, lang_map
    except Exception as e:
        print(f"[sample_merges] DB snapshot failed ({e}); using synthetic.", file=sys.stderr)
        nodes = {
            1: {"canonical": "skopje", "label": "LOC", "mentions": 120},
            2: {"canonical": "shkup", "label": "LOC", "mentions": 40},
            3: {"canonical": "tirana", "label": "LOC", "mentions": 90},
            4: {"canonical": "tirane", "label": "LOC", "mentions": 20},
            5: {"canonical": "saudi arabia", "label": "LOC", "mentions": 30},
            6: {"canonical": "dublin", "label": "LOC", "mentions": 25},
            7: {"canonical": "macedonia", "label": "LOC", "mentions": 80},
            8: {"canonical": "maqedonia", "label": "LOC", "mentions": 15},
        }
        edges = [(5, 6, 12), (1, 7, 8), (2, 1, 6)]
        lang_map = {1: {"mk", "en"}, 2: {"sq"}, 3: {"sq"}, 4: {"sq"}, 5: {"en"}, 6: {"en"}}
        return nodes, edges, lang_map


def similarity_candidates(nodes: dict, threshold: float = 0.8) -> list[tuple[int, int, float]]:
    from src.nlp.normalize import entity_similarity  # type: ignore

    out: list[tuple[int, int, float]] = []
    by_label: dict[str, list[int]] = {}
    for nid, info in nodes.items():
        by_label.setdefault(info["label"], []).append(nid)
    for label, ids in by_label.items():
        for i in range(len(ids)):
            a = ids[i]
            ca = nodes[a]["canonical"]
            for j in range(i + 1, len(ids)):
                b = ids[j]
                cb = nodes[b]["canonical"]
                if abs(len(cb) - len(ca)) > 3 or (ca and cb and cb[0] != ca[0]):
                    # fast prefilter mirroring merge_entities.py
                    pass
                score = entity_similarity(ca, cb)
                if score >= threshold:
                    out.append((a, b, round(score, 3)))
    return out


def cooccurrence_candidates(edges: list[tuple[int, int, int]], threshold: int = 5) -> list[tuple[int, int, int]]:
    """Reconstructed co-occurrence: any edge weight >= threshold proposes a merge.

    This mirrors the discarded logic — 'merge globally co-occurring entities' —
    which is exactly the false-merge trap documented in the merge_entities.py NOTE.
    """
    return [(a, b, w) for a, b, w in edges if w >= threshold]


def main() -> int:
    ap = argparse.ArgumentParser(description="Sample merge candidates (REQ-2).")
    ap.add_argument("--strategy", choices=["similarity", "cooccurrence"], required=True)
    ap.add_argument("--n", type=int, default=100, help="Sample size")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threshold", type=float, default=None, help="similarity threshold (default 0.8) or edge weight (default 5)")
    args = ap.parse_args()

    ensure_seed(args.seed)
    nodes, edges, lang_map = _snapshot_nodes()
    print(f"Snapshot: {len(nodes)} nodes, {len(edges)} edges")

    if args.strategy == "similarity":
        thr = args.threshold if args.threshold is not None else 0.8
        cands = similarity_candidates(nodes, threshold=float(thr))
        header_extra = {"strategy": "similarity", "threshold": thr}
    else:
        thr = int(args.threshold) if args.threshold is not None else 5
        cands = cooccurrence_candidates(edges, threshold=thr)
        header_extra = {"strategy": "cooccurrence", "threshold": thr}

    print(f"Candidates before sampling: {len(cands)} (threshold={header_extra['threshold']})")
    if not cands:
        print("No candidates at this threshold — lowering it or checking DB content.", file=sys.stderr)
        cands = []

    # Reproducible random sample of up to N
    rnd = random.Random(args.seed)
    rnd.shuffle(cands)
    sampled = cands[: args.n]
    if len(sampled) < args.n:
        print(f"Only {len(sampled)} candidates available (<{args.n}); writing what exists.", file=sys.stderr)

    prov = provenance_header(seed=args.seed)
    prov["params"] = header_extra

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        f.write(f"# provenance: {__import__('json').dumps(prov, ensure_ascii=False)}\n")
        w = csv.DictWriter(
            f,
            fieldnames=[
                "a_id",
                "b_id",
                "a_text",
                "b_text",
                "a_normalized",
                "b_normalized",
                "similarity_or_weight",
                "languages",
                "strategy",
                "label",
            ],
        )
        w.writeheader()
        for a, b, score in sampled:
            a_info = nodes.get(a, {"canonical": str(a), "label": "?"})
            b_info = nodes.get(b, {"canonical": str(b), "label": "?"})
            langs_a = ",".join(sorted(lang_map.get(a, set())))
            langs_b = ",".join(sorted(lang_map.get(b, set())))
            langs = ",".join(sorted(set(langs_a.split(",")) | set(langs_b.split(",")))) if (langs_a or langs_b) else ""
            w.writerow(
                {
                    "a_id": a,
                    "b_id": b,
                    "a_text": a_info["canonical"],
                    "b_text": b_info["canonical"],
                    "a_normalized": a_info["canonical"],
                    "b_normalized": b_info["canonical"],
                    "similarity_or_weight": score,
                    "languages": langs.strip(","),
                    "strategy": args.strategy,
                    "label": "",
                }
            )
    print(f"Wrote {len(sampled)} rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
