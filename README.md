# News Intelligence — North Macedonia

Self-hosted pipeline that ingests Macedonian / Albanian / English / Turkish news
feeds, runs sentiment + multilingual NER, and builds a searchable **knowledge
graph**. Designed to run 24/7 on a Raspberry Pi 4B (8 GB) via Docker Compose.

## Architecture

| Service   | Image (built from `.`) | RAM   | Role |
|-----------|------------------------|-------|------|
| `postgres`| `pgvector/pgvector:pg16` | 1 GB | PG + vector + FTS (trigger) |
| `worker`  | `news-intelligence-worker` | 1 GB | scheduler + fetch + extract + sentiment |
| `ner`     | `news-intelligence-worker` | 2 GB | GLiNER2 ONNX NER + graph build (model in `hf_cache`) |
| `web`     | `news-intelligence-web` | 512 MB | FastAPI (`/search`, `/analytics`, `/graph`, …) |
| `dashboard`| `news-intelligence-dashboard` | 512 MB | Streamlit UI (Pipeline / Explore / Sentiment / Entities / Graph) |

Pipeline status flow per article:
`new → fetched → extracted → sentiment_done → analyzed`.
`worker` does fetch→extract→sentiment; `ner` consumes `sentiment_done` → `analyzed`.

## Prerequisites (Pi)

- Raspberry Pi 4B, 8 GB RAM, Raspberry Pi OS (64-bit)
- Docker + Docker Compose v2 (`sudo apt install docker.io docker-compose-plugin`)
- ~6 GB free disk: ~1.5 GB × 2 images + ~1.2 GB NER model (`hf_cache`) + Postgres data
- Outbound internet for feeds and the one-time model download

## Build (on the build machine / laptop)

```bash
docker compose build            # normal build; source changes are picked up automatically
# only add --no-cache if you edit the Dockerfile or Python dependencies
```

## Transfer images to the Pi

Option A — save/load over SSH (no registry needed):

```bash
docker compose build
docker save news-intelligence-worker news-intelligence-web news-intelligence-dashboard \
  pgvector/pgvector:pg16 | gzip > ni_images.tar.gz
scp ni_images.tar.gz pi@<PI_IP>:/tmp/
ssh pi@<PI_IP> 'docker load < /tmp/ni_images.tar.gz'
```

Option B — run `docker compose build` directly on the Pi (slower, needs build context + network).

## First run on the Pi

```bash
# 1. Start the database first and wait for healthy
docker compose up -d postgres
docker compose ps            # wait until postgres is "healthy"

# 2. Apply migrations (creates tables up to revision 004)
docker compose run --rm worker -m alembic upgrade head

# 3. Start everything
docker compose up -d
```

`hf_cache` is a named volume shared only by the `ner` service. The GLiNER2 ONNX
model downloads **once** on the first `ner` run (~1.2 GB, ~20–30 min on the Pi)
and then persists across restarts/rebuilds. Watch it:

```bash
docker compose logs -f ner    # first run shows the model download, then "NER service started"
```

## Validate the live pipeline (smoke test)

**Quick check** — ingestion + extraction + sentiment + language detection, no model
load. Safe to run on the `worker` container:

```bash
docker compose run --rm worker -m src.workers.smoke
```

**Full check** — also runs NER + knowledge graph. Downloads the model once into
`hf_cache` (warms it for the real `ner` service). Run on the `ner` container:

```bash
NEWS_SMOKE_NER=1 docker compose run --rm ner -m src.workers.smoke
```

Both print a `=== SMOKE TEST SUMMARY ===` with article / entity / graph counts.
Optional env: `NEWS_SMOKE_SOURCES=<n>` (limit sources), `NEWS_SMOKE_ITERS=<n>`.

## Verify it's working

```bash
curl -s http://localhost:8000/health
curl -s "http://localhost:8000/analytics/overview?days=7" | head
curl -s "http://localhost:8000/sentiment/distribution"
```

Open the dashboard at **http://\<PI_IP\>:8501** (Explore tab = search & trends;
Knowledge Graph tab = entity network).

## Operations

- **Logs:** `docker compose logs -f <service>` (worker | ner | web | dashboard)
- **Restart one service:** `docker compose restart ner`
- **Stop:** `docker compose down` (keeps `pgdata` + `hf_cache` volumes)
- **Backups (Postgres):** snapshot nightly, e.g.
  ```bash
  docker compose exec -T postgres pg_dump -U news news_intelligence > backup_$(date +%F).sql
  # restore: docker compose exec -T postgres psql -U news -d news_intelligence < backup.sql
  ```
- **Model backup:** `hf_cache` lives in a Docker volume; back it up once with
  `docker run --rm -v ni_hf_cache:/data -v $PWD:/out busybox tar czf /out/hf_cache.tar.gz -C /data .`

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `ner` stays busy ~20–30 min on first start | Normal — GLiNER2 model download. Wait; it persists in `hf_cache`. |
| `articles_failed` > 0 in smoke | Bad feed / blocked site. Check `docker compose logs worker`; disable the source in `config/sources.yml`. |
| Sentiment all `neutral` for MK/SQ/TR | Expected for general text — the lexicon only catches strong political/news vocabulary. |
| NER finds little | GLiNER2 is multilingual but recall varies; entity graph still builds from whatever is extracted. |
| Dashboard shows no graph | Run the full smoke (`NEWS_SMOKE_NER=1`) or let `ner` process articles first. |
| `pg_isready` healthcheck fails | Postgres not healthy yet / wrong password in `NEWS_DATABASE_URL`. |
