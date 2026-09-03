# Annotation Guideline — Entity Extraction (REQ-1.8)

**Freeze date:** fill before first annotation session. Changing this doc after annotation starts invalidates earlier work.

## 1. Label set (REQ-1.5)

Confirm against `src/nlp/ner.py:DEFAULT_LABELS` + `LABEL_MAP` before annotating.
Current paper label set: **PERSON (PER), ORG, LOCATION (LOC)**. Do not annotate MISC/EVENT/DATE even if the model predicts them — map only the three.

| Paper label | GLiNER raw labels | Note |
|---|---|---|
| PERSON | `person`, `persons`, `PER` | Named people, including transliterated variants. |
| ORG | `organization`, `organizations`, `ORG` | Companies, institutions, parties, media outlets. |
| LOCATION | `location`, `locations`, `LOC`, `city`, `country` | Cities, regions, countries, geographic features. |

If GLiNER config adds a synonym, record the mapping here and freeze.

## 2. Span rules (REQ-1.6)

- Annotate **character offsets** `[start, end)` in the raw `text` field (no normalization).
- One span per entity mention; overlapping mentions are separate rows.
- Include the full surface form as it appears: honorifics excluded (`President Ivanov` → `Ivanov`), but include particles that are part of the name.
- Use Label Studio / doccano / spreadsheet — pick one, document it in `eval/README.md:Tool choice`.

## 3. Edge cases (freeze these before annotating)

1. **"the Macedonian government"** → ORG? **Yes** — government as institution is ORG. Lowercase `government` still qualifies when it denotes the institution.
2. **Demonyms** (`Macedonians`, `Shqiptarët`) → NOT annotated as LOCATION. Treat as community reference, exclude unless used as a toponym.
3. **Adjectival forms** (`Macedonian wine`) → NOT an entity unless the adjective itself is the entity name.
4. **Abbreviations** (`VMRO-DPMNE`, `EU`, `NATO`) → ORG/LOC by referent, keep exact abbreviation span.
5. **Multi-word names** (`North Macedonia`, `New York`) → single span covering the full name.
6. **Nested names** (`University of Skopje, Faculty of Law`) → outermost org only; do not double-annotate the city inside.
7. **Transliterated duplicates** (`Скопје` vs `Skopje`) → annotate both as they appear; normalization is evaluated separately.
8. **Dates/events** (`Independence Day`) → DO NOT annotate (out of scope).
9. **Ambiguous LOC vs ORG** (`Macedonia` as country vs team) → label by context (LOC for geography, ORG only if clearly an organization).
10. **Punctuation/digits inside** (`Skopje-1`) → include only the name portion (`Skopje`), unless the digit is part of the official name.

Add new edge cases only as an appendix with date — never retroactively change prior annotations.

## 4. Quality bar

- Annotator: 1 primary per language minimum. If ≥2 annotators, double-annotate ≥20% per language and compute Cohen's κ; report in the paper.
- Before bulk work: all annotators label the same 5-article pilot; reconcile differences; update this doc once, then freeze.

## 5. Output schema (REQ-1.9)

One JSONL object per article, matching export schema + `entities`:

```json
{"article_id": "123", "language": "mk", "source": "Meta.mk", "title": "...", "text": "...", "published_at": "...", "entities": [{"start": 10, "end": 16, "type": "LOCATION", "text": "Skopje"}]}
```
