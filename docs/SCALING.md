# Scaling NER horizontally

The `ner` service enriches articles (entity extraction + knowledge-graph construction)
and is the heaviest stage in the pipeline. It is built to scale **horizontally** — you
run multiple `ner` containers and they share the same database without any extra
coordination.

This page covers *why* it's safe, *how* to scale it, *how* to tune it, and the caveats.

## Why it's safe to run many replicas

`src/workers/ner_service.py` claims work with a Postgres row lock:

```python
select(Article)
.where(Article.status.in_(["sentiment_done", "ner_running"]), ...)
.limit(batch_size)
.with_for_update(skip_locked=True)
```

`SKIP LOCKED` means each replica only ever sees articles that no other replica has
locked. Two `ner` containers can therefore never process the same article, and there is
no shared queue, message broker, or leader election to configure.

The upstream `worker` service does **not** run NER — it only does fetch / extract /
sentiment and then flips an article to `sentiment_done`. The `ner` service consumes
those. So NER is fully decoupled and can be scaled independently.

Each replica loads its own copy of the GLiNER2 ONNX model (a lazy singleton inside the
process), so N replicas ≈ N model copies in RAM.

## Scale out

The `ner` service has no published ports and no fixed `container_name`, so Compose can
replicate it directly:

```bash
docker compose up -d --scale ner=4
```

Up/down later, same command with a different `N`:

```bash
docker compose up -d --scale ner=6
docker compose up -d --scale ner=1
```

> You can also bake a default into `docker-compose.yml` via `deploy: { replicas: 4 }`,
> but that only takes effect under Docker Swarm or `docker compose up --compatibility`.
> The `--scale` flag works on plain Compose, so it's the recommended path.

## Tuning

All NER tuning lives on the `ner` service in `docker-compose.yml` (and is read by
`src/workers/ner_service.py` from env, with the legacy defaults kept as fallbacks).

| Setting | Default | Purpose |
|---------|---------|---------|
| `OMP_NUM_THREADS` | `2` | Cap OpenMP threads **per replica**. |
| `ORT_NUM_THREADS` | `2` | Cap ONNX Runtime threads **per replica**. |
| `NEWS_NER_BATCH_SIZE` | `30` (compose sets `50`) | Articles claimed per cycle — raise to keep replicas busy. |
| `NEWS_NER_POLL_INTERVAL` | `5` (compose sets `2`) | Seconds the loop sleeps between cycles — lower to reduce idle gap. |
| `NEWS_NER_ZOMBIE_MIN` | `5` | Reclaim `ner_running` articles stuck longer than this. |
| `NEWS_NER_MAX_RETRIES` | `3` | NER retries before marking an article `failed`. |

### CPU thread caps

GLiNER2 runs on CPU via ONNX Runtime, which by default uses **all** available cores. If
you run N replicas each using all cores, they thrash. Cap the per-replica threads so the
total stays at or below your core count:

```
N × OMP_NUM_THREADS  ≲  cores
```

Example — 8 cores, 4 replicas → `OMP_NUM_THREADS=2` / `ORT_NUM_THREADS=2` (4×2 = 8).
16 cores, 6 replicas → `OMP_NUM_THREADS=2` (6×2 = 12 ≤ 16).

## Sizing

- **RAM:** each `ner` replica needs ~1.5–2 GB (`mem_limit: 2g` in compose). Budget
  `N × 2 GB` and keep room for the other services (postgres 1 GB, worker 1 GB,
  embeddings 2 GB, web/alerts ~1 GB).
  - 16 GB laptop → `N=4` (~8 GB NER) is comfortable; `N=5–6` only if you see free RAM.
- **Don't scale the `worker`.** It runs the scheduler; multiple `worker` instances
  would duplicate feed fetches. `ner` is the only safe `--scale` target. (If sentiment
  itself becomes the bottleneck, that's a separate tuning task, not a `--scale`.)
- **Docker Desktop (macOS):** the default Docker VM is ~2 GB RAM / few cores. Raise
  **Settings → Resources → Memory to ~12–14 GB** (and CPU to ~8) first, or every
  replica gets OOM-killed. Native Linux Docker is fine as-is.

## Verify

```bash
docker compose logs --tail=20 ner
# expect: "NER cycle: N articles analyzed" appearing across -ner-1 … -ner-4
```

Watch the backlog drain:

```bash
docker compose exec postgres psql -U news -d news_intelligence \
  -c "SELECT status, count(*) FROM articles GROUP BY status ORDER BY 2 DESC;"
```

`sentiment_done` should fall as `analyzed` rises. Throughput ≈ `N ×` the single-replica
rate.

## Caveats

- **Story assignment is eventual-consistency.** `assign_story` clusters articles into
  `stories` (events) by shared-entity overlap. Concurrent replicas may rarely create a
  duplicate story cluster for the same emerging event. This is a soft issue (not a
  crash) and can be reconciled later; it does not affect entity extraction or the graph.
- **Cold-start burst.** Every replica loads the GLiNER2 model at boot, spiking CPU/IO.
  The shared `hf_cache` volume means the weights are only downloaded once, but each
  process still has to load them into memory.
- **Per-replica serial processing.** Within one container, articles are processed one at
  a time. Horizontal scaling (more containers) is the primary lever; if you also want
  more throughput *per* replica, that requires intra-process batching/threading work on
  `src/nlp/ner.py` and is out of scope here.
