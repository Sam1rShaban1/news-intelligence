# News Intelligence — North Macedonia

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
- **Analytics & dashboards** — REST API + a Streamlit UI with pipeline status, search &
  trends, sentiment distribution, top entities, an interactive entity graph, and a stories
  view.

---

## Architecture

All services are defined in `docker-compose.yml` and built from the single `Dockerfile`
(`build: .`). They share one Postgres database and talk over the compose network.

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
> fetch/extract/sentiment.

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
 Dashboards─│ dashboard│ ────────────────────────────────────┘
 & API ────→│ web(API) │
            └──────────┘
```

---

## Technology stack

- **Language / runtime:** Python 3.12 (slim).
- **Web framework:** FastAPI + Uvicorn.
- **Frontend:** React 19 + Vite + Tailwind CSS v4 (SPA, served by nginx); interactive knowledge-graph via the bundled chart kit. Talks to the API through an nginx reverse proxy at `/api`.
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
> — not from model-level batching.

---

## NLP / ML pipeline (in detail)

### 1. Fetch (`src/workers/fetch.py`)
The worker polls enabled sources from `config/sources.yml`, discovers article URLs
(parallelised with a `ThreadPoolExecutor`), downloads and extracts clean text with
`newspaper4k`, and stores `Article` rows. Language is detected per article.

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
and served by nginx. It is the primary UI, replacing the old Streamlit dashboard. nginx
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

The UI falls back to bundled mock data when the backend is unreachable, so it renders even
before ingestion has produced anything.

The app source lives in `ui/` (`Dockerfile`, `nginx.conf`, `vite.config.ts`, `src/`). It is
built and run automatically by `docker compose up`.

---

## Configuration

### Environment variables (`NEWS_*` prefix, see `config/settings.py`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEWS_DATABASE_URL` | `postgresql://news:news@localhost:5432/news_intelligence` | DB connection (compose uses the `postgres` service host). |
| `NEWS_POLL_INTERVAL_SECONDS` | `60` | Worker poll interval. |
| `NEWS_BATCH_SIZE` | `10` | Articles claimed per cycle (NER uses `30`). |
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

> The Docker image **bakes** the sentiment ONNX + tokenizer into `/app/models` at build
> time (see `Dockerfile`), so `NEWS_SENTIMENT_MODEL=transformer` works out of the box.

### Sources (`config/sources.yml`)

List of feeds, grouped by language. Each entry:

```yaml
- name: Meta.mk (MK)
  url: https://meta.mk
  rss: https://meta.mk/feed/
  enabled: true        # set false to disable without deleting
```

The `seed` service loads this on first start. Disable a misbehaving feed by setting
`enabled: false` and restarting (or re-running the seed job).

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

1. Build on the laptop, then transfer images (no registry needed):

   ```bash
   docker compose build
    docker save news-intelligence-worker news-intelligence-web \
      news-intelligence-frontend pgvector/pgvector:pg16 | gzip > ni_images.tar.gz
   scp ni_images.tar.gz pi@<PI_IP>:/tmp/
   ssh pi@<PI_IP> 'docker load < /tmp/ni_images.tar.gz'
   ```

2. On the Pi:

   ```bash
   docker compose up -d postgres
   docker compose ps            # wait until postgres is "healthy"
   docker compose up -d        # migrate + seed run automatically, then all services start
   ```

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

- **Logs:** `docker compose logs -f <service>` (`worker | ner | web | dashboard`).
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

---

## Known limitations

- **Cross-language entity synonyms are intentionally NOT auto-merged.** `shkup`
  (Albanian) and `skopje` (Macedonian) denote the same city but have very different
  surface forms, so they remain **separate nodes**. We validated that a general
  multilingual sentence embedder (`paraphrase-multilingual-MiniLM-L12-v2`) scores this
  pair only ~0.53 and risks new false merges for Balkan geography, and that co-occurrence
  merging is unsafe (it fused unrelated entities). The robust fix is **entity linking to a
  Knowledge Base** (Wikidata/DBpedia) or a curated seed-alignment set — both out of scope
  for the current low-resource deployment. Inflectional / near-spelling variants
  (`shkup`/`shkupi`/`shkupit`, `macedonia`/`maqedonia`, `kosova`/`kosovo`) *are* merged
  by the similarity backfill.
- **NER recall varies** by language; the graph is only as rich as what GLiNER2 extracts.
- **Sentiment** with the lexicon fallback is coarse (strong political/news vocabulary);
  the transformer model is more balanced but still a general-purpose sentiment model.
- **`stories`** are clustered heuristically by shared entities, not by full semantic
  similarity.

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
├── docker-compose.yml         # postgres, migrate, seed, worker, ner, web, dashboard
├── config/
│   ├── settings.py            # NEWS_* env configuration
│   └── sources.yml            # RSS feed list (per language)
├── alembic/                   # DB migrations (001–007)
├── src/
│   ├── api/                   # FastAPI app + routes (articles, search, analytics,
│   │                         #   entities, sentiment, graph, stories)
│   ├── dashboard/             # Streamlit UI
│   ├── db/                    # SQLAlchemy models + session
│   ├── nlp/                   # normalize, ner, graph, relations, stories, sentiment_onnx
│   └── workers/               # fetch/extract/sentiment loop + ner_service + lifecycle
└── scripts/                   # seed_sources.py, backfill_search_vector.py, merge_entities.py
```
