# Contributing

Thanks for your interest in improving News Intelligence! This is a self-hosted,
local-first news analysis platform (Python backend + React frontend).

## Prerequisites

- Docker + Docker Compose (recommended for a full local stack)
- Python 3.12+ (for backend work without Docker)
- Node 18+ and [pnpm](https://pnpm.io/) (for frontend work)
- PostgreSQL 16 + `pgvector` (provided by the Compose stack)

## Running the stack locally

```bash
# Bring up everything: postgres, migrate, seed, worker, ner, web, frontend
docker compose up -d

# Frontend:  http://localhost:8501   API: http://localhost:8000
```

The first `ner` start downloads the GLiNER2 ONNX model into the `hf_cache`
volume (~20–30 min). The sentiment ONNX model is baked into the image.

## Backend development (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export NEWS_DATABASE_URL=postgresql://news:news@localhost:5432/news_intelligence
alembic upgrade head            # create schema in your Postgres
pytest -q                       # run tests
ruff check .                    # lint
```

See `.env.example` for all `NEWS_*` configuration variables.

## Frontend development

```bash
cd ui
pnpm install
pnpm build                      # production bundle (served by nginx)
# or: pnpm dev                   # Vite dev server with HMR
```

## Workflow

1. Branch off `main` (`git checkout -b feat/short-name`).
2. Make your change. Keep commits focused.
3. Run `ruff check .` and `pytest -q` (backend) / `pnpm build` (frontend) before
   pushing.
4. Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`,
   `fix:`, `docs:`, `chore:`, `ci:`, `style:`, `refactor:`, `test:`).
5. Open a PR describing the change and the motivation. CI must be green.

## Database migrations

Schema changes go through Alembic:

```bash
alembic revision -m "describe change"   # edit upgrade()/down_revision
alembic upgrade head
```

## Tests

- Backend unit tests live in `tests/` and run under `pytest` (no external services
  required for the pure-function tests). Route tests that touch the database use a
  Postgres instance (provided as a service in CI).
- Keep new backend behaviour covered by a test where practical.

## Code style

- `ruff` is the linter/formatter; config lives in `pyproject.toml` (line-length 100).
- Type hints are expected on new functions.

## License

By contributing, you agree your contributions are licensed under the
[Apache License 2.0](LICENSE).
