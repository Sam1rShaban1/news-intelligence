# eval — LREC-COLING Section 5 evaluation harness

Implements **all five experiments** in `Evaluation Requirements Specification draft v1`. Every script is runnable with a single command, writes a **REQ-0.1 provenance header** (date, commit, hardware, image tags), and is deterministic where sampling is involved (REQ-0.4).

> Paper rule: no result goes into `main.tex` without its raw artifact committed here (or linked from the private data repo) — REQ-0.2. Tables are **auto-generated** from script output — REQ-1.14/2.10/3.11/4.12.

## Hardware note (REQ-0.5)

If any experiment cannot be completed with real hardware/data (e.g. no physical Pi), the paper text must say so explicitly. Simulated runs emit `simulate=true` in the header and a stderr warning — do not cite simulated numbers as measured.

## Setup

```bash
# From the repo root, with the production/staging DB reachable:
cp .env.example .env   # ensure NEWS_DATABASE_URL is set
docker compose up -d   # worker + ner + postgres + web should be healthy
```

All scripts auto-fallback to a synthetic stub when the DB/ML deps are absent, so they still run in CI — but synthetic numbers must not go in the paper.

## Deliverables checklist (Section 7)

- [x] `eval/README.md` — this file
- [x] `eval/eval_ner.py` + gold/predictions JSONL
- [x] `eval/eval_merging.py` + two labeled CSVs
- [x] `eval/bench_scaling.py` + `reset_batch.py`/`.sql` + raw CSV
- [x] `eval/bench_search.py` + query lists + raw CSV
- [x] `eval/pi_resource.py` → `eval/pi_resource_log.csv` + summary
- [x] `eval/annotation_guideline.md` (REQ-1.8)
- [ ] Inter-annotator κ (filled after double-annotation, REQ-1.7)
- [x] All tables auto-generated from scripts

## Execution order (Section 6)

1. **Scaling throughput** — pure ops, no annotation
2. **Search latency** — pure ops
3. **Entity extraction annotation** — bottleneck, needs guideline frozen first
4. **Merge accuracy** — needs entity snapshot from step 3's model run
5. **Pi resource usage** — needs physical Pi or matched VM, mostly unattended

Recommended: `1 → 2 → 5 (parallel/unattended) → 3 → 4`.

---

## 0. Provenance (REQ-0.1)

Every result file starts with:

```json
{"_provenance": {"date_run": "...", "git_commit": "...", "hardware": {...}, "docker_images": {...}, "seed": 42}}
```

or for CSVs: `# provenance: {...}` as the first line. Utility: `eval/utils.py:provenance_header()`.

---

## 1. Entity Extraction Quality (Table 1) — REQ-1.1–1.14

**Annotation guideline:** `eval/annotation_guideline.md` — freeze before annotating.

```bash
# Sample 200 articles stratified by source, 40% cap per REQ-1.2
# Run inside the worker image so DB/ML deps are present (host needs venv otherwise):
docker compose run --rm worker eval/sample_articles.py --out eval/articles.jsonl --seed 42
# host fallback (requires local `pip install -r requirements/base.lock` + .env):
python eval/sample_articles.py --out eval/articles.jsonl --seed 42

# Run the pinned ner image against that batch (REQ-1.10–1.11)
# Image ENTRYPOINT is `python`, so do not prefix `python` again:
docker compose run --rm worker eval/run_ner.py --in eval/articles.jsonl --out eval/predictions.jsonl
# host fallback:
python eval/run_ner.py --in eval/articles.jsonl --out eval/predictions.jsonl

# Gold: after annotating articles.jsonl via Label Studio/doccano, export as eval/gold.jsonl
# (schema REQ-1.9: same objects plus entities: [{start,end,type,text}])

# Score (strict exact match primary, relaxed IoU>0.5 optional)
python eval/eval_ner.py --gold eval/gold.jsonl --pred eval/predictions.jsonl --out eval/table1.csv --tex eval/table1.tex
python eval/eval_ner.py --gold eval/gold.jsonl --pred eval/predictions.jsonl --out eval/table1_relaxed.csv --relaxed
```

| REQ | Covered |
|---|---|
| 1.1 50×4 sample | `sample_articles.py --per-lang 50` |
| 1.2 40% source cap | enforced, cap reported |
| 1.3 randomized analyzed | `ORDER BY` + shuffle, seed 42 |
| 1.4 JSONL export | `articles.jsonl` |
| 1.5 labels PER/ORG/LOC | `src/nlp/ner.py:LABEL_MAP` + `annotation_guideline.md` |
| 1.6 span offsets | guideline + gold schema |
| 1.7 inter-annotator κ | compute after 20% overlap |
| 1.8 guideline | `annotation_guideline.md` |
| 1.9 output format | gold.jsonl + `entities` |
| 1.10 pinned image | `--image-tag` in header; run inside worker image |
| 1.11 direct endpoint | `run_ner.py` calls `extract_entities` directly |
| 1.12 exact vs relaxed | `--relaxed` flag, strict default |
| 1.13 per-lang/type P/R/F1 | `eval_ner.py` |
| 1.14 script output | `eval/table1.csv` + `eval/table1.tex` |

Expected runtime: sampling <10s; NER predictions ~10–30 min for 200 articles (GLiNER cold start included); scoring <1s.

---

## 2. Entity Resolution / Merge Accuracy (Table 2) — REQ-2.1–2.10

```bash
# Same snapshot for both strategies (REQ-2.6) — run inside the image so both see the DB:
docker compose run --rm worker eval/sample_merges.py --strategy similarity --n 100 --seed 42 --out eval/merges_similarity.csv
docker compose run --rm worker eval/sample_merges.py --strategy cooccurrence --n 100 --seed 42 --out eval/merges_cooccurrence.csv
# host fallback:
# DRY_RUN=1 python eval/sample_merges.py --strategy similarity --n 100 --seed 42 --out eval/merges_similarity.csv
# python eval/sample_merges.py --strategy cooccurrence --n 100 --seed 42 --out eval/merges_cooccurrence.csv

# Manual labelling: fill `label` per row with correct_merge / false_merge / ambiguous

# Score (host is fine):
python eval/eval_merging.py --sim eval/merges_similarity.csv --co eval/merges_cooccurrence.csv --out eval/table2.csv --tex eval/table2.tex
```

Output: `% correct / false / ambiguous` per strategy + 3–5 example pairs (REQ-2.9) printed for the appendix.

Expected runtime: <10s per sampler + manual labelling (~1 day for 200 pairs).

---

## 3. Scaling Throughput (Table 3) — REQ-3.1–3.11

```bash
# One-time: pick the 500-article batch (same IDs across all runs, REQ-3.4)
docker compose run --rm worker eval/reset_batch.py --pick --out eval/bench_ids.txt
cat eval/bench_ids.txt | wc -l   # 500

# Verify no stray sentiment_done before timing (REQ-3.5)
docker compose run --rm worker eval/reset_batch.py --drain-check
docker compose stop worker        # pause pipeline to avoid contamination

# Full benchmark: 1,2,4 replicas × 3 runs = 9 timed runs (REQ-3.8)
# Bench needs Docker control — run on host (or --simulate for CI demo):
python eval/bench_scaling.py --replicas 1,2,4 --runs 3 --out eval/scaling_raw.csv

# Manual alternative (if you prefer SQL):
# psql $NEWS_DATABASE_URL -c "UPDATE articles SET status='sentiment_done' WHERE id = ANY(ARRAY[...])"
# docker compose up -d --scale ner=1  # then time until all 500 are analyzed

# Results
cat eval/scaling_raw.csv
cat eval/scaling_raw_table3.tex   # LaTeX for Table 3
```

- Fixed hardware (REQ-3.1) — document cores/RAM/VM type; only `ner` replica count changes (REQ-3.2).
- `docker compose up -d --scale ner=N` (REQ-3.6); start timer at reset completion (REQ-3.7); mean+std over 3 runs (REQ-3.8); restart `ner` between counts (REQ-3.9).
- Columns `replica_count,run_number,articles_per_min,elapsed_seconds` + summary mean/speedup (REQ-3.11).

Expected runtime: depends on throughput; 9× 500-article drains. Budget ~2–3 hours on a 4-core VM.

---

## 4. Search Latency (REQ-4.1–4.12)

```bash
# Queries committed for reproducibility (REQ-4.6)
cat eval/queries_same_script.txt
cat eval/queries_cross_script.txt

# Benchmark the live /search endpoint (REQ-4.7), with warmup (REQ-4.8)
python eval/bench_search.py --same eval/queries_same_script.txt --cross eval/queries_cross_script.txt --out eval/search_raw.csv --api http://localhost:8000

# With API key:
NEWS_API_KEY=... python eval/bench_search.py --api http://localhost:8000 --api-key $NEWS_API_KEY --out eval/search_raw.csv

# Results
cat eval/search_raw.csv
cat eval/search_raw_table.tex
```

Reports `p50/p95` per category + corpus count `N` (REQ-4.1/4.12). Warmup, wall-clock latency per query (REQ-4.9), same hardware as REQ-3 if possible (REQ-4.10).

Expected runtime: <1 min for 100+100 queries.

---

## 5. Resource Usage on Pi tier (REQ-5.1–5.9)

```bash
# On a real Raspberry Pi 4B 8GB if at all possible (REQ-5.1)
docker compose -f docker-compose.pi.yml up -d
python eval/pi_resource.py --duration 3600 --interval 10 --out eval/pi_resource_log.csv
# Or: deploy and measure in one step:
python eval/pi_resource.py --deploy --compose-file docker-compose.pi.yml --duration 3600 --out eval/pi_resource_log.csv

# Simulate (for CI / VM substitute — paper must state this explicitly per REQ-5.1):
python eval/pi_resource.py --simulate --duration 600 --out eval/pi_resource_log.csv
```

- Realistic 1-hour sustained workload (REQ-5.4), not a cold-start snapshot.
- `docker stats` every 10s (REQ-5.5); report peak + mean per service (REQ-5.6); total peak with headroom (REQ-5.7).
- Output `eval/pi_resource_log.csv` (REQ-5.8) + summary table (REQ-5.9).

Expected runtime: 1 hour attended/unattended.

---

## Single-command per script

| Script | Invocation | Output |
|---|---|---|
| `sample_articles.py` | `docker compose run --rm worker eval/sample_articles.py --out eval/articles.jsonl` | `eval/articles.jsonl` |
| `run_ner.py` | `docker compose run --rm worker eval/run_ner.py --in eval/articles.jsonl --out eval/predictions.jsonl` | `eval/predictions.jsonl` |
| `eval_ner.py` | `python eval/eval_ner.py --gold eval/gold.jsonl --pred eval/predictions.jsonl --out eval/table1.csv` | `eval/table1.csv` + `eval/table1.tex` |
| `sample_merges.py` | `DRY_RUN=1 python eval/sample_merges.py --strategy similarity --out eval/merges_similarity.csv` | `eval/merges_*.csv` |
| `eval_merging.py` | `python eval/eval_merging.py --sim eval/merges_similarity.csv --co eval/merges_cooccurrence.csv --out eval/table2.csv` | `eval/table2.csv` + `eval/table2.tex` |
| `reset_batch.py` | `python eval/reset_batch.py --pick --out eval/bench_ids.txt` | `eval/bench_ids.txt` |
| `bench_scaling.py` | `python eval/bench_scaling.py --out eval/scaling_raw.csv` | `eval/scaling_raw.csv` + `eval/scaling_raw_table3.tex` |
| `bench_search.py` | `python eval/bench_search.py --out eval/search_raw.csv` | `eval/search_raw.csv` + `eval/search_raw_table.tex` |
| `pi_resource.py` | `python eval/pi_resource.py --out eval/pi_resource_log.csv` | `eval/pi_resource_log.csv` + `*_summary.tex` |

## Inter-annotator agreement (REQ-1.7 / 2.5)

After double-annotating ≥20% per language, compute Cohen's κ:

```bash
python -c "from sklearn.metrics import cohen_kappa_score; print(cohen_kappa_score(a_labels, b_labels))"
```

Report the number in the paper even for the overlap subset.
