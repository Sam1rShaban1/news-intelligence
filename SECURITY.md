# Security Policy

## Supported versions

| Version | Supported          |
| ------- | ------------------ |
| `main`  | :white_check_mark: |
| older   | :x:                |

News Intelligence is released continuously from `main`. Security fixes land on
`main` and are included in the next image build.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

- Use **GitHub Private Vulnerability Reporting**: open the
  *Security* tab on the repository and choose *Report a vulnerability*.

Include as much detail as you can:

- A description of the vulnerability and its impact.
- Steps to reproduce, or a proof-of-concept.
- Affected version / commit.
- Any suggested mitigation.

You will receive an acknowledgement within a few business days. Once the issue is
triaged we will coordinate a fix and a disclosure timeline with you.

## Scope & notes

News Intelligence is a **self-hosted** tool: operators are responsible for
securing their own deployment (network exposure, credentials, the Postgres
database, and the `NEWS_*` configuration). This policy covers vulnerabilities in
the code in this repository, not misconfigurations of a self-hosted instance.

**Deployment hardening checklist for operators:**
- Change the default `POSTGRES_PASSWORD` (`news`) before exposing any service
  beyond `127.0.0.1`/loopback. The API and Postgres are bound to loopback by
  default in the compose files; only the `frontend` (port 8501) is the intended
  public entry point.
- Set `NEWS_API_KEY` (and keep it out of version control) so the API is not
  unauthenticated. The nginx frontend injects it into proxied `/api` requests.
- Do not place the `frontend` port on an untrusted network without `NEWS_API_KEY`
  set.

The application bundles third-party ML models (GLiNER2, XLM-RoBERTa sentiment,
VADER) and libraries — see the `NOTICE` file for attribution. Vulnerabilities in
those upstream components should be reported to their respective maintainers.

## Accepted dependency risks

CI (`pip-audit`, blocking) ignores the following IDs. Each entry must state why
the risk is accepted and when to revisit it.

- **PYSEC-2026-3740** (`nltk==3.10.3`, GHSA-8mgp-746c-j5xp / CVE-2026-81726):
  pathsec sandbox bypass in NLTK model-artifact APIs (`TransitionParser.train` /
  `parse`, `AveragedPerceptron.save` / `load`, `PerceptronTagger.save_to_json`,
  `save_maxent_params`). Exploitation requires the application to enable pathsec
  enforcement *and* let untrusted callers choose model import/export paths.
  This repo uses NLTK only for tokenizer corpora (`punkt`, `punkt_tab`,
  `averaged_perceptron_tagger`) consumed by `newspaper4k` — those APIs are never
  called, let alone with caller-controlled paths. Upstream has **no patched
  release** (PyPI latest is 3.10.3), so upgrading is not an option.
  **Revisit:** drop the `--ignore-vuln` in `ci.yml` as soon as NLTK publishes a
  fixed version and re-pin `requirements/*.lock`.
