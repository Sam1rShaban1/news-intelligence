# News Intelligence — North Macedonia

[![CI](https://github.com/Sam1rShaban1/news-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/Sam1rShaban1/news-intelligence/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org)
[![Deployment](https://img.shields.io/badge/deployment-docker--compose-0db7ed.svg)](docker-compose.yml)

A self-hosted, multilingual news intelligence platform for **North Macedonia** that
ingests Macedonian, Albanian, English and Turkish news feeds 24/7, enriches every
article with sentiment and multilingual Named-Entity Recognition (NER), and builds a
**searchable knowledge graph** of people, organisations, locations and the events that
connect them.

It is designed to run on modest hardware (a Raspberry Pi 4B, 8 GB, no GPU) and is fully
containerised with Docker Compose.

---

## What it does

- **Multi-source ingestion** — pulls RSS/Atom feeds across 4 languages (MK / SQ / EN / TR),
  extracts article text, and de-duplicates by URL.
- **Sentiment analysis** — per-article sentiment (positive / negative / neutral) using a
  multilingual XLM-RoBERTa transformer served as an ONNX model, with a VADER/lexicon
  fallback for speed or when the model is unavailable.
- **Multilingual NER** — extracts entities (PER, ORG, LOC, MISC) with **GLiNER2** (ONNX),
  which works across all four languages without per-language models.
- **Knowledge graph** — resolves entities into canonical nodes, records co-occurrence
  edges, extracts relationship triples, and clusters articles into **stories** (events).
- **Full-text search** — lexical search over article text with cross-script support
  (Macedonian Cyrillic is transliterated to Latin so a Latin query finds Cyrillic articles).
- **Analytics & frontend** — REST API + a React frontend with pipeline status, search &
  trends, sentiment distribution, top entities, an interactive entity graph, and a stories
  view.

---

## Architecture

All services are defined in `docker-compose.yml` and built from the multi-stage
`Dockerfile`. The default `vps` target installs the full stack (multilingual GLiNER2
NER + baked ONNX sentiment + `pgvector`); `docker compose build --target pi` (or
`docker-compose.pi.yml`) builds a lightweight image for a Raspberry Pi that omits the
heavy ML stack and disables NER/embeddings via the `FEATURE_*` flags. They share one
Postgres database and talk over the compose network.

| Service     | Image (built from `.`)          | RAM     | Role |
|-------------|--------------------------------|---------|------|
| `postgres`  | `pgvector/pgvector:pg16`       | 1 GB    | PostgreSQL 16 + `pgvector` + full-text search. Persistent `pgdata` volume. |
| `migrate`   | same image                     | —       | One-shot `alembic upgrade head` (runs before worker/ner at startup). |
| `seed`      | same image                     | —       | One-shot `scripts/seed_sources.py` (loads `config/sources.yml`). |
| `worker`    | `news-intelligence-worker`      | 1 GB    | Scheduler + fetch + extract + sentiment. |
| `ner`       | `news-intelligence-worker`      | 2 GB    | GLiNER2 ONNX NER + knowledge-graph construction (model cached in `hf_cache`). |
| `web`       | `news-intelligence-web`         | 512 MB  | FastAPI REST API (`:8000`). |
| `frontend` | `news-intelligence-frontend`     | 128 MB  | React + Vite + Tailwind SPA (nginx) on `:8501`; proxies `/api/*` → `web:8000`. |

> The `worker` and `ner` services use the **same image** but different commands
> (`src.workers` vs `src.workers.ner_service`) so the heavy NER model never blocks
> fetch/extract/sentiment. The `ner` service is also **horizontally scalable** — run
> several replicas with `docker compose up --scale ner=N` (see
> *Operations → Scaling NER horizontally*); it claims work with a Postgres row lock so
> replicas never double-process the same article.

### Data-flow / status state machine

Per article:

```
new → fetched → extracted → sentiment_done → analyzed
```

- **`worker`** drives `new → fetched → extracted → sentiment_done`.
- **`ner`** consumes `sentiment_done` articles and drives `sentiment_done → analyzed`.
- Each transition is committed in a single transaction; a failed article is retried
  (up to `max_retries`) and otherwise marked `failed`. Zombie articles (claimed but
  stuck longer than `zombie_timeout_minutes`) are reclaimed.

```
            ┌──────────┐   fetch/extract/sentiment   ┌──────────────┐
 RSS feeds →│ worker   │ ───────────────────────────→│  postgres    │
            └──────────┘                              │  articles    │
                                   sentiment_done     │              │
            ┌──────────┐   NER + graph build          │              │
 GLiNER2 ──→│ ner      │ ───────────────────────────→│  entities /  │
            └──────────┘                              │  graph /     │
                                                      │  stories     │
             ┌──────────┐   read APIs                   └──────┬───────┘
 Frontend──│frontend│ ────────────────────────────────────┘
 & API ────→│ web(API) │
             └──────────┘
```

---

## Technology stack

- **Language / runtime:** Python 3.12 (slim).
- **Web framework:** FastAPI + Uvicorn.
- **Frontend:** React 19 + Vite + Tailwind CSS v4 (SPA, served by nginx); interactive knowledge-graph rendered on a custom `<canvas>` with `d3-force` + `d3-zoom` (layout runs in a web worker). Talks to the API through an nginx reverse proxy at `/api`.
- **ORM / migrations:** SQLAlchemy 2.x + Alembic.
- **Database:** PostgreSQL 16 with `pgvector` (for future embedding use) and built-in
  full-text search.
- **NER:** `gliner2-onnx` running the multilingual **GLiNER2** model
  (`lmo3/gliner2-multi-v1-onnx`) on CPU via ONNX Runtime.
- **Sentiment:** `onnxruntime` + a pre-exported **int8 XLM-RoBERTa** ONNX model
  (`onnx-community/twitter-xlm-roberta-base-sentiment-ONNX`, ~279 MB) + `tokenizers`;
  VADER (`vaderSentiment`) as a lexicon fallback.
- **Article extraction:** `newspaper4k` (with `lxml`, `feedparser` for discovery).
- **Scheduling:** `apscheduler` (inside the worker).

> **GLiNER2 constraint:** its `extract_entities(text, labels, threshold)` accepts a
> *single* string (no native batching). NER throughput therefore comes from bulk DB
> writes, a larger `batch_size`, ONNX thread tuning, and incremental story assignment
> — and, most effectively, by running multiple `ner` replicas (see
> *Operations → Scaling NER horizontally*).

---

## Third-party models & attribution

This project bundles and depends on open-source models and libraries. Their
respective licenses apply; see the `LICENSE` (Apache-2.0) and `NOTICE` files for
the full attribution.

**Machine-learning models**

| Component | Use | Source | License |
|-----------|-----|--------|---------|
| **GLiNER2** (`lmo3/gliner2-multi-v1-onnx`) | Multilingual NER (ONNX) | [huggingface.co/lmo3/gliner2-multi-v1-onnx](https://huggingface.co/lmo3/gliner2-multi-v1-onnx) | Apache-2.0 |
| **XLM-RoBERTa sentiment** (`onnx-community/twitter-xlm-roberta-base-sentiment-ONNX`, int8) | Per-article sentiment (ONNX) | [huggingface.co/onnx-community/twitter-xlm-roberta-base-sentiment-ONNX](https://huggingface.co/onnx-community/twitter-xlm-roberta-base-sentiment-ONNX) | MIT* |
| **VADER** (`vaderSentiment`) | Lexicon sentiment fallback | [github.com/cjhutto/vaderSentiment](https://github.com/cjhutto/vaderSentiment) | MIT |

\* Derived from `cardiffnlp/twitter-xlm-roberta-base-sentiment`, built on XLM-RoBERTa
(Meta, MIT).

**Key libraries**

- **Backend:** ONNX Runtime (MIT), FastAPI / Uvicorn / Pydantic (MIT), SQLAlchemy +
  Alembic (MIT), `newspaper4k` (MIT), `feedparser` (BSD), APScheduler (MIT),
  `pgvector` (Apache-2.0), `psycopg2` (LGPL-3.0).
- **Frontend:** React / React DOM / Vite / Tailwind CSS (MIT), `d3-force` / `d3-zoom`
  / `d3-selection` (BSD-3-Clause), `louvain` / js-louvain (MIT).

If you redistribute this software, retain the `NOTICE` file and the attributions
above.

---

## NLP / ML pipeline (in detail)

### 1. Fetch (`src/workers/fetch.py`)
The worker polls enabled, non-deleted sources, discovers article URLs
(parallelised with a `ThreadPoolExecutor`), downloads and extracts clean text with
`newspaper4k`, and stores `Article` rows. Language is detected per article. Sources are
managed from the **Sources** UI (add / enable / disable / soft-delete / test a feed);
`config/sources.yml` is only the initial seed. User-supplied feed URLs are validated by an
SSRF guard that blocks non-http(s) and internal/loopback addresses.

### 2. Extract + Sentiment (`src/workers/extract.py`, `src/nlp/sentiment_onnx.py`)
- **Full-text index** is built here: `article.search_vector = to_tsvector('simple',
  normalize_text(f"{title} {content}"))` (see *Search* below). The old PL/pgSQL trigger
  was removed (migration `007_fts_fix`) — the index is now owned by Python so it can use
  the transliterated normalisation.
- **Sentiment** is computed by `src/nlp/sentiment_onnx.py`. With
  `NEWS_SENTIMENT_MODEL=transformer` it runs the multilingual XLM-RoBERTa ONNX model;
  `auto` (default) uses the transformer when the model file is present, otherwise the
  VADER lexicon; `lexicon` forces VADER. ONNX is configured with
  `intra_op_num_threads` capped (so it doesn't starve the rest of the Pi).

### 3. NER + Knowledge graph (`src/workers/ner_service.py`, `src/nlp/*`)
The `ner` service claims `sentiment_done` articles in batches and, per article:

1. **Extract entities** with GLiNER2 (`src/nlp/ner.py`).
2. **Resolve & store nodes** (`src/nlp/graph.py`): each raw mention is normalised
   (`normalize_entity`) and attached to a canonical `EntityNode`; mentions are stored in
   the `entities` table.
3. **Co-occurrence edges** (`entity_edges`): every pair of distinct nodes in an article
   increments an undirected edge weight.
4. **Relationship triples** (`src/nlp/relations.py` → `relationships` table): simple
   subject–verb–object extraction over the article.
5. **Story assignment** (`src/nlp/stories.py`): articles are clustered into `stories`
   (events) incrementally — a new article is assigned to the best-matching existing story
   by shared entity overlap, or starts a new story. Full recomputation is available via
   `recompute=True` (backfill).

### 4. Entity normalisation & resolution (`src/nlp/normalize.py`, `scripts/merge_entities.py`)
This is the de-duplication layer. Two stages:

- **Per-mention normalisation** (`normalize_entity`) — applied at extraction time, it:
  - transliterates **Macedonian Cyrillic → Latin** (official RNM transliteration),
  - folds **Turkish / Albanian** diacritics & special letters to ASCII
    (`İ→i`, `ë→e`, `ş→s`, `ç→c`, `ğ→g`, …),
  - strips combining marks, lowercases, and removes digits/punctuation
    (`skopje12` → `skopje`, `north-macedonia` → `north macedonia`).
  This already collapses most surface-form variants (e.g. `Скопје` → `skopje`,
  `Tiranë` → `tirane`) at zero cost.

- **Similarity-based backfill** (`scripts/merge_entities.py`) — a **reviewable, opt-in**
  job that merges residual near-duplicate nodes (inflectional / near-spelling variants
  such as `shkup` / `shkupi` / `shkupit`, `macedonia` / `maqedonia`,
  `kosova` / `kosovo`, `ohrid` / `ohrida`). It merges by **normalised-text similarity**
  only (threshold `SIMILARITY_THRESHOLD`, default **0.8**, overridable via env), never by
  co-occurrence. Run it with `DRY_RUN=1` to preview, then without to apply:

  ```bash
  DRY_RUN=1 docker compose run --rm worker scripts/merge_entities.py
  docker compose run --rm worker scripts/merge_entities.py
  ```

> **Design note / lesson learned.** Co-occurrence-based merging was tried and **rejected**:
> in news, entities that appear in the same article are normally *different* entities in
> the same story, so global co-occurrence merging produced absurd false merges
> (e.g. *Saudi Arabia* merged into *Dublin*). The current approach merges only by
> string/normalisation similarity, which is safe. See *Known limitations* for the
> cross-language case.

### 5. Search (`src/api/routes/search.py`)
Lexical search over `search_vector` using `websearch_to_tsquery('simple', …)` with the
query first passed through `normalize_text`, so Latin queries also match transliterated
Cyrillic articles.

---

## REST API (`web`, port 8000)

Base path `/`. Returns JSON. Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check. |
| GET | `/articles` | List articles (pagination, filters: language, status, source, date). |
| GET | `/articles/{id}` | Single article. |
| GET | `/search?q=` | Full-text search (normalised, cross-script). |
| GET | `/analytics/overview` | Aggregate counts, per-language/per-day activity, top sources. |
| GET | `/sentiment/distribution` | Sentiment histogram (overall + by language). |
| GET | `/sentiment/recent` | Recent articles with sentiment. |
| GET | `/entities` | List entity nodes (filters: label, query, limit). |
| GET | `/entities/top` | Top entities by mention count. |
| GET | `/entities/stats` | Entity type distribution. |
| GET | `/entities/nodes` | Batch node lookup (for the graph UI). |
| GET | `/entities/{node_id}/articles` | Articles mentioning a node. |
| GET | `/entities/{node_id}/relationships` | Relationship triples for a node. |
| GET | `/graph/cooccurrence` | Co-occurrence edges (for graph rendering). |
| GET | `/graph/stats` | Graph size stats. |
| GET | `/graph/relationships` | Relationship triples. |
| GET | `/stories` | Event clusters (entities, article counts, sentiment). |
| GET | `/stories/{id}` | Single story with its articles. |

Quick checks:

```bash
curl -s http://localhost:8000/health
curl -s "http://localhost:8000/analytics/overview?days=7" | head
curl -s "http://localhost:8000/sentiment/distribution"
curl -s "http://localhost:8000/search?q=skopje" | head
```

---

## Web frontend (`frontend`, port 8501)

A lightweight React 19 + Vite + Tailwind CSS v4 single-page app, built to a static bundle
and served by nginx. It is the primary UI, replacing the previous Streamlit-based dashboard. nginx
proxies `/api/*` to the `web` (FastAPI) service, so the browser only ever talks to one
origin.

Views:

- **Overview** — KPI cards, sentiment-over-time, language mix, trending entities.
- **Explore** — full-text search with language / sentiment / source / entity / date filters.
- **Sentiment** — sentiment distribution (overall + by language) and recent sentiment.
- **Entities** — searchable entity directory (PER / ORG / LOC) with an entity inspector
  (mentioning articles + relationships).
- **Graph** — interactive knowledge-graph (entity co-occurrence network) with an entity
  inspector.
- **Stories** — event clusters with their articles and dominant sentiment.

The UI shows an error state when the backend is unreachable, so it renders meaningfully
only once ingestion has produced data.

The app source lives in `ui/` (`Dockerfile`, `nginx.conf`, `vite.config.ts`, `src/`). It is
built and run automatically by `docker compose up`.

## Screenshots

Captured from a local deployment (`docker compose up`); the PNGs live in
[`docs/screenshots/`](docs/screenshots/).

| Overview | Explore | Sentiment |
| -------- | ------- | --------- |
| ![Overview](docs/screenshots/overview.png) | ![Explore](docs/screenshots/explore.png) | ![Sentiment](docs/screenshots/sentiment.png) |

| Entities | Graph | Stories |
| -------- | ----- | ------- |
| ![Entities](docs/screenshots/entities.png) | ![Graph](docs/screenshots/graph.png) | ![Stories](docs/screenshots/stories.png) |

| Sources | Watchlist | Alerts |
| ------- | --------- | ------ |
| ![Sources](docs/screenshots/sources.png) | ![Watchlist](docs/screenshots/watchlist.png) | ![Alerts](docs/screenshots/alerts.png) |

---

## Configuration

All services are configured through `NEWS_*` environment variables (loaded by
`config/settings.py`, with overrides from a local `.env` file). A ready-to-copy
template is provided in [`.env.example`](.env.example).

### Environment variables (`NEWS_*` prefix, see `config/settings.py`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEWS_DATABASE_URL` | `postgresql://news:news@localhost:5432/news_intelligence` | DB connection (compose uses the `postgres` service host). |
| `NEWS_POLL_INTERVAL_SECONDS` | `60` | Worker poll interval. |
| `NEWS_BATCH_SIZE` | `10` | Articles claimed per cycle by the `worker` (sentiment stage). The `ner` service uses its own `NEWS_NER_BATCH_SIZE` (below). |
| `NEWS_ZOMBIE_TIMEOUT_MINUTES` | `5` | Reclaim stuck articles after this. |
| `NEWS_MAX_RETRIES` | `3` | Retries before marking `failed`. |
| `NEWS_HTTP_TIMEOUT` | `15` | HTTP timeout for fetches. |
| `NEWS_USER_AGENT` | `NewsIntelligence/0.1` | UA for fetches. |
| `NEWS_SCAN_INTERVAL_MINUTES` | `60` | Source re-scan interval. |
| `NEWS_LOG_LEVEL` | `INFO` | Logging level. |
| `NEWS_CONFIG_DIR` | `config` | Where `sources.yml` lives. |
| `NEWS_GLINER_MODEL` | `lmo3/gliner2-multi-v1-onnx` | GLiNER2 ONNX model repo. |
| `NEWS_SENTIMENT_MODEL` | `auto` | `auto` \| `transformer` \| `lexicon`. |
| `NEWS_SENTIMENT_MODEL_PATH` | `/app/models/sentiment.onnx` | Transformer ONNX path. |
| `NEWS_NER_BATCH_SIZE` | `30` | Articles claimed per NER cycle (set to `50` on the `ner` service in `docker-compose.yml`). |
| `NEWS_NER_POLL_INTERVAL` | `5` | Seconds the NER loop sleeps between cycles (set to `2` in compose). |
| `NEWS_NER_ZOMBIE_MIN` | `5` | Reclaim `ner_running` articles stuck longer than this. |
| `NEWS_NER_MAX_RETRIES` | `3` | NER retries before marking an article `failed`. |

> The Docker image **bakes** the sentiment ONNX + tokenizer into `/app/models` at build
> time (see `Dockerfile`), so `NEWS_SENTIMENT_MODEL=transformer` works out of the box.

### Security

- **Ports are loopback-bound by default.** `docker-compose.yml` publishes Postgres
  (`5432`) and the API (`8000`) on `127.0.0.1` only; only the `frontend` (`:8501`) is
  reachable from the host network. On a VPS, keep it that way and put the stack behind a
  reverse proxy / firewall — **never** expose `5432` or `8000` to the public internet,
  and override `POSTGRES_PASSWORD` in your `.env` (the default `news`/`news` credentials
  are well-known). See `SECURITY.md` for the threat model.
- **Optional API key.** Set `NEWS_API_KEY` in `.env` to require an `X-API-Key` header on
  every API route except `/health`. The nginx frontend injects the key into proxied
  `/api` requests automatically, so the browser UI works without ever holding the secret.
  Leave it empty to disable auth (trusted-network / single-tenant use).
- **Non-root containers.** Every service image drops to an unprivileged `app` user, and
  the baked sentiment model is verified against a pinned `sha256` at build time
  (supply-chain hardening).
- **SSRF guard.** User-supplied feed URLs are validated to block non-http(s) and
  internal/loopback addresses — see *NLP / ML pipeline → Fetch*.

### Sources (`config/sources.yml`)

List of feeds, grouped by language. Each entry:

```yaml
- name: Meta.mk (MK)
  url: https://meta.mk
  rss: https://meta.mk/feed/
  enabled: true        # set false to disable without deleting
```

The `seed` service loads this on first start as the initial source set. Once running,
manage sources from the **Sources** tab in the UI: add new feeds, toggle `enabled`, run a
live feed test, or soft-delete a source (stops fetching and hides it, but keeps its
historical articles). Soft-deleted sources can be restored via the API
(`PATCH /sources/{id}` with `enabled: true` and `deleted: false`).

---

## Database & migrations

SQLAlchemy models under `src/db/models/`. Alembic migrations under `alembic/versions/`:

| # | Migration | Adds |
|---|-----------|------|
| 001 | initial | `articles`, `sources`. |
| 002 | entities_sentiment | per-article `sentiment_label`/`sentiment_score`, `entities` table. |
| 003 | knowledge_graph | `entity_nodes`, `entity_edges`. |
| 004 | relationship_triples | `relationships`. |
| 005 | stories | `stories`, `story_articles` (event clusters). |
| 006 | performance_indexes | GIN index on `stories.entity_node_ids`; B-tree on `entity_nodes(label, mention_count DESC)`, `entity_edges(weight DESC)`, `articles(language)`, `articles(sentiment_label)`, `stories(language)`, `stories(dominant_sentiment)` — keeps the API/graph fast. |
| 007 | fts_fix | drops the old `search_vector` PL/pgSQL trigger; FTS is now Python-owned (`to_tsvector('simple', normalize_text(...))`). |
| 008 | entity_wikidata | `entity_nodes` external-id columns (`wikidata_id`, `wikipedia_url`, `description`, `merge_target_id`) for entity resolution. |
| 009 | source_deleted | `sources.deleted` soft-delete flag + indexes on `enabled`/`deleted`. |

The `migrate` service runs `alembic upgrade head` automatically at startup (and
`worker`/`ner` wait for it), so no manual migration step is needed.

---

## Build & deploy

### On a laptop / build machine

```bash
docker compose build            # source + Dockerfile changes are picked up automatically
# add --no-cache only if you edit Python deps or the Dockerfile
```

### Running locally (laptop)

```bash
docker compose up -d
# frontend: http://localhost:8501   API: http://localhost:8000
```

### Deploying to a Raspberry Pi 4B (8 GB)

Use the lightweight `pi` build target — `docker-compose.pi.yml` builds the `pi`
Docker target (no ONNX / pgvector), disables NER + embeddings via the `FEATURE_*`
flags, and uses plain `postgres:16`. Fetch/extract/sentiment (VADER + mk/sq/tr
lexicon) still run, along with de-duplication, merge, and the full web UI + API.

1. Build on the laptop, then transfer images (no registry needed):

   ```bash
   docker compose -f docker-compose.pi.yml build --target pi
   docker save news-intelligence-worker news-intelligence-web \
     news-intelligence-frontend postgres:16 | gzip > ni_pi_images.tar.gz
   scp ni_pi_images.tar.gz pi@<PI_IP>:/tmp/
   ssh pi@<PI_IP> 'docker load < /tmp/ni_pi_images.tar.gz'
   ```

2. On the Pi:

   ```bash
   docker compose -f docker-compose.pi.yml up -d postgres
   docker compose -f docker-compose.pi.yml ps   # wait until postgres is "healthy"
   docker compose -f docker-compose.pi.yml up -d # migrate + seed run automatically, then services start
   ```

> On the Pi there is **no `ner` service** (entity extraction / knowledge-graph
> building are disabled) and sentiment uses VADER + the mk/sq/tr lexicon (no
> transformer model). On a VPS, use the default `docker-compose.yml`
> (`build --target vps`) for full multilingual GLiNER2 NER + baked sentiment
> transformer + vector embeddings.

### First-run notes

- **GLiNER2 model download:** the `ner` service downloads GLiNER2 ONNX into the
  `hf_cache` volume **once** (~1.2 GB; ~20–30 min on a Pi, fast on a laptop) and caches
  it across restarts. Watch with `docker compose logs -f ner`.
- **Sentiment model** is already baked into the image (`/app/models`), so no download is
  needed for sentiment.
- Disk budget on the Pi: ~1.5 GB × 2 images + ~1.2 GB GLiNER cache + Postgres data
  (~6 GB free recommended).

---

## Operations

- **Logs:** `docker compose logs -f <service>` (`worker | ner | web | frontend`).
- **Restart one service:** `docker compose restart ner`.
- **Stop (keeps data):** `docker compose down` — the `pgdata` and `hf_cache` volumes
  persist.
- **Backups:**
  ```bash
  docker compose exec -T postgres pg_dump -U news news_intelligence > backup_$(date +%F).sql
  # restore: docker compose exec -T postgres psql -U news -d news_intelligence < backup.sql
  ```
  Back up the `hf_cache` volume once:
  ```bash
  docker run --rm -v news-intelligence_hf_cache:/data -v $PWD:/out busybox \
    tar czf /out/hf_cache.tar.gz -C /data .
  ```

### Validate the live pipeline (smoke tests)

**Quick check** — ingestion + extraction + sentiment + language detection (no model
load), safe on `worker`:

```bash
docker compose run --rm worker -m src.workers.smoke
```

**Full check** — also runs NER + graph build (downloads the model once into `hf_cache`):

```bash
NEWS_SMOKE_NER=1 docker compose run --rm ner -m src.workers.smoke
```

Both print a `=== SMOKE TEST SUMMARY ===` with article / entity / graph counts.
Optional env: `NEWS_SMOKE_SOURCES=<n>`, `NEWS_SMOKE_ITERS=<n>`.

### Scaling NER horizontally

The `ner` service is designed to scale out. It claims work with a Postgres row lock
(`SELECT … FOR UPDATE SKIP LOCKED`) on `sentiment_done` / `ner_running` articles, so
any number of replicas are mutually safe — no shared queue, no coordination, and no
double-processing. Each replica loads its own GLiNER2 ONNX model (~1.5–2 GB RAM).

Run N replicas with Compose's scale flag (the `ner` service has no published ports and
no fixed container name, so this works out of the box):

```bash
docker compose up -d --scale ner=4
```

Scale up/down later the same way (`--scale ner=<N>`). A fuller guide, including thread
tuning and sizing math, is in [`docs/SCALING.md`](docs/SCALING.md).

**Tuning (set on the `ner` service in `docker-compose.yml`):**

| Setting | Why |
|---------|-----|
| `OMP_NUM_THREADS` / `ORT_NUM_THREADS` | Cap ONNX/OpenMP threads **per replica** so N replicas don't oversubscribe the CPU. Keep `N × threads ≲ cores` (default `2`). |
| `NEWS_NER_BATCH_SIZE` | Articles claimed per cycle — raise to keep replicas busy (default `30`; compose sets `50`). |
| `NEWS_NER_POLL_INTERVAL` | Seconds between cycles — lower to reduce idle gap (default `5`; compose sets `2`). |

**Sizing:** total NER RAM ≈ `N × 2 GB`. On a 16 GB laptop, `N=4` (~8 GB) leaves
headroom for the other services; push to `N=5–6` only if you see free RAM. **Do not
scale the `worker` service** — it runs the scheduler, so multiple instances would
duplicate feed fetches. `ner` is the only safe `--scale` target.

> **Docker Desktop (macOS):** the default Docker VM is ~2 GB RAM / few cores. Raise
> **Settings → Resources → Memory to ~12–14 GB** (and CPU to ~8) or every replica gets
> OOM-killed. Native Linux Docker is fine as-is.

**Verify it's working:**

```bash
docker compose logs --tail=20 ner   # expect "NER cycle: N articles analyzed" across -ner-1 … -ner-4
docker compose exec postgres psql -U news -d news_intelligence \
  -c "SELECT status, count(*) FROM articles GROUP BY status ORDER BY 2 DESC;"
```

`sentiment_done` should drain; throughput ≈ `N ×` the single-replica rate.

**Caveats:**
- *Story assignment is eventual-consistency* (`assign_story`): concurrent replicas may
  rarely spawn a duplicate story cluster. Soft issue, not a crash; reconcilable later.
- *Cold-start burst:* all replicas load the ONNX model at boot (CPU/IO spike), but the
  shared `hf_cache` volume avoids re-downloading the weights.

---

## Known limitations

- **Cross-language entity synonyms are intentionally NOT auto-merged.** `shkup`
  (Albanian) and `skopje` (Macedonian) denote the same city but have very different
  surface forms, so they remain **separate nodes**. We validated that a general
  multilingual sentence embedder (`paraphrase-multilingual-MiniLM-L12-v2`) scores this
  pair only ~0.53 and risks new false merges for Balkan geography, and that co-occurrence
  merging is unsafe (it fused unrelated entities). The robust fix is **entity linking to a
  Knowledge Base**. Wikidata linking is now available as an optional step
  (`scripts/link_wikidata.py`, also wired into the worker scheduler every 30 min) and
  cross-lingual synonyms that resolve to the same Q-id can be merged with
  `scripts/merge_by_wikidata.py`; a curated seed-alignment set remains an alternative.
  Inflectional / near-spelling variants
  (`shkup`/`shkupi`/`shkupit`, `macedonia`/`maqedonia`, `kosova`/`kosovo`) *are* merged
  by the similarity backfill.
- **NER recall varies** by language; the graph is only as rich as what GLiNER2 extracts.
- **Sentiment** with the lexicon fallback is coarse (strong political/news vocabulary);
  the transformer model is more balanced but still a general-purpose sentiment model.
- **`stories`** are clustered heuristically by shared entities, not by full semantic
  similarity.
- **Alerts are in-app only** in this release — alert rules are evaluated and shown on
  the Alerts page, but there is no email / Slack / push delivery yet.

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `ner` busy ~20–30 min on first start | Normal — GLiNER2 model download into `hf_cache`. Wait; it persists. |
| `articles_failed` > 0 | Bad/blocked feed. Check `docker compose logs worker`; disable the source in `config/sources.yml`. |
| Sentiment all `neutral` for MK/SQ/TR | Expected with the lexicon fallback; switch to `NEWS_SENTIMENT_MODEL=transformer`. |
| NER finds little | GLiNER2 recall varies by language; the graph still builds from whatever is extracted. |
| Frontend graph / stories empty | Run the full smoke (`NEWS_SMOKE_NER=1`) or let `ner` process articles first. |
| Cyrillic search misses | Ensure `search_vector` is populated — re-run `scripts/backfill_search_vector.py` if needed. |
| `pg_isready` healthcheck fails | Postgres not healthy yet / wrong password in `NEWS_DATABASE_URL`. |

---

## Project layout

```
.
├── Dockerfile                 # single image for all services
├── docker-compose.yml         # postgres, migrate, seed, worker, ner, web, frontend
├── config/
│   ├── settings.py            # NEWS_* env configuration
│   └── sources.yml            # RSS feed list (per language)
├── alembic/                   # DB migrations (001–007)
├── ui/                       # React + Vite + Tailwind frontend (SPA), served by nginx
├── src/
│   ├── api/                   # FastAPI app + routes (articles, search, analytics,
│   │                         #   entities, sentiment, graph, stories)
│   ├── db/                    # SQLAlchemy models + session
│   ├── nlp/                   # normalize, ner, graph, relations, stories, sentiment_onnx
│   └── workers/               # fetch/extract/sentiment loop + ner_service + lifecycle
└── scripts/                   # seed_sources.py, backfill_search_vector.py, merge_entities.py
```
