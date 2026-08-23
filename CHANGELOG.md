# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-08-23

First public release of News Intelligence — a self-hosted, multilingual news
intelligence platform for North Macedonia (MK / SQ / EN / TR).

### Added
- **Multilingual ingestion** — RSS/Atom feeds across 4 languages, article-text
  extraction, and URL-based de-duplication.
- **Sentiment analysis** — multilingual XLM-RoBERTa sentiment served as an ONNX
  model, with a VADER/lexicon fallback for speed or when the model is absent.
- **Multilingual NER** — GLiNER2 (ONNX) entity extraction (PER/ORG/LOC/MISC)
  across all four languages without per-language models.
- **Knowledge graph** — canonical entity nodes, co-occurrence edges, relationship
  triples, and **story** (event) clustering.
- **Full-text search** — lexical search with cross-script support (Macedonian
  Cyrillic transliterated to Latin).
- **REST API** — articles, search, analytics, sentiment, entities, graph,
  stories, sources, alerts, watchlist, and export endpoints.
- **React frontend** — Overview, Explore, Sentiment, Entities, Graph, Stories,
  Sources, Watchlist, and Alerts views, served by nginx.
- **Watchlist + alert rules** — track entities and define keyword / entity /
  language / sentiment-threshold alerts (surfaced in-app on the Alerts page).
- **Exports** — CSV/JSON article/search/story export and server-side PDF export.
- **Semantic search + embeddings** (optional, `vps` tier, pgvector-backed).
- **Horizontal NER scaling** — run multiple `ner` replicas via
  `docker compose up --scale ner=N`; the service claims work with a Postgres
  row lock so replicas never double-process. Env-tunable batch size, poll
  interval, and ONNX thread caps.

### Security
- Postgres and the API are published on `127.0.0.1` by default; only the
  frontend is reachable from the host network.
- Optional `NEWS_API_KEY` (constant-time compare); the nginx frontend injects it
  into proxied `/api` requests so the browser never holds the secret.
- Containers run as a non-root `app` user.
- The baked sentiment model is verified against a pinned `sha256` at build time.
- User-supplied feed URLs are validated by an SSRF guard (blocks non-http(s) and
  internal/loopback addresses).
- Reproducible builds via compiled, fully-pinned dependency lockfiles
  (`requirements/base.lock`, `requirements/vps.lock`); Dependabot enabled.

### Notes
- Alerts are **in-app only** in this release — there is no email/Slack/push
  delivery yet; alert rules are evaluated and shown on the Alerts page.
- Translation between the four languages is not performed; articles are analysed
  in their original language.

[0.1.0]: https://github.com/Sam1rShaban1/news-intelligence/releases/tag/v0.1.0
