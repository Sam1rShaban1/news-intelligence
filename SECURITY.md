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
- If that is unavailable, email the maintainers at **security@news-intelligence.example**
  (replace `example` with the real TLD) and encrypt if possible.

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

The application bundles third-party ML models (GLiNER2, XLM-RoBERTa sentiment,
VADER) and libraries — see the `NOTICE` file for attribution. Vulnerabilities in
those upstream components should be reported to their respective maintainers.
