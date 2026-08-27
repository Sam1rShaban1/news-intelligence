# Roadmap

This document outlines planned and considered work for News Intelligence. Items are
roughly ordered by priority; nothing here is a commitment — priorities may shift based
on contributor interest and real-world usage.

See [CHANGELOG.md](CHANGELOG.md) for what has already shipped.

---

## Near term

- **Alert delivery (webhooks / email / Slack)** — alert rules are evaluated in-app
  today; add outbound channels so operators can react without checking the dashboard.
- **Region packs** — documented starter configs (feed lists + normalisation notes) beyond
  the North Macedonia reference deployment; community contributions welcome.
- **"Use your region" guide** — expand the README section into a full doc for swapping
  feeds, extending transliteration rules, and tuning lexicon sentiment for new languages.

## Medium term

- **UI internationalisation (i18n)** — the backend handles multiple languages; the
  dashboard UI is English-only today. Add locale files and a language switcher.
- **Semantic search UX** — embeddings and pgvector are wired in; expose semantic
  nearest-neighbour search prominently in Explore (alongside lexical search).
- **Entity linking improvements** — broaden Wikidata coverage, document the
  `link_wikidata` → `merge_by_wikidata` workflow, and surface linked entities in the UI.
- **Kubernetes / Helm chart** — optional deployment path for operators who outgrow a
  single Compose host (horizontal NER scaling is already Postgres-coordinated).

## Longer term / exploring

- **Live public demo** — read-only hosted instance with sample data so newcomers can
  explore before self-hosting.
- **Plugin / extractor hooks** — allow custom article extractors or enrichment steps
  without forking the core pipeline.
- **Translation layer (optional)** — cross-language article summaries or query expansion;
  articles stay in their original language by default.
- **Coverage & E2E tests** — Playwright smoke tests against a Compose stack in CI;
  enforce minimum backend coverage thresholds.

## Out of scope (for now)

- **Hosted SaaS** — this project is self-hosted first; a managed offering is not planned.
- **Real-time streaming ingestion** — RSS polling is the model; WebSocket / social firehoses
  are not on the roadmap unless someone contributes an adapter.
- **Automatic cross-language entity merging without a knowledge base** — co-occurrence and
  embedding-only merging were tried and rejected; Wikidata linking is the supported path.

---

Have an idea? Open a [feature request](.github/ISSUE_TEMPLATE/feature_request.yml) or
start a [Discussion](https://github.com/Sam1rShaban1/news-intelligence/discussions) if
you want to explore a design before coding.
