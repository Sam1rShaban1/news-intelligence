"""Wikidata entity linking for canonical entity nodes.

Resolves a canonical entity (`EntityNode`) to a Wikidata Q-id so the knowledge
graph can (a) expose a stable, language-independent identifier + Wikipedia link,
and (b) merge cross-lingual synonyms that share a Q-id (e.g. `shkup` / `skopje`).

Uses the public Wikidata `wbsearchentities` API over stdlib `urllib` (no extra
dependency). Network failures are non-fatal: the function returns `None` and the
caller retries later.
"""

import json
import logging
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

from src.nlp.normalize import normalize_entity

logger = logging.getLogger(__name__)

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "NewsIntelligence/0.1 (https://github.com/news-intelligence)"

# Minimum score for a candidate to be accepted as a match.
MATCH_THRESHOLD = 1.5

# Politeness: max retries on HTTP 429 and the backoff cap (seconds).
_MAX_RETRIES = 4
_RETRY_BASE_DELAY = 1.0
_RETRY_MAX_DELAY = 30.0

# Light type hints: entity label -> keywords looked for in the candidate description.
_TYPE_HINTS = {
    "PER": ("human", "person", "politician", "singer", "actor", "writer", "athlete"),
    "ORG": ("organization", "company", "university", "agency", "party", "institution"),
    "LOC": ("city", "country", "river", "mountain", "region", "town", "municipality"),
}


@dataclass
class Candidate:
    qid: str
    label: str
    description: str
    aliases: list[str]


def _wikidata_request(url: str) -> dict | None:
    """GET a Wikidata JSON endpoint with 429/Retry-After backoff.

    Returns parsed JSON, or `None` on non-recoverable network/HTTP/decode errors.
    HTTP 429 (rate limited) is retried with an exponential backoff capped by the
    server's `Retry-After` header, so a batch linking run does not get IP-blocked.
    """
    for attempt in range(_MAX_RETRIES):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < _MAX_RETRIES - 1:
                retry_after = e.headers.get("Retry-After")
                try:
                    delay = min(float(retry_after), _RETRY_MAX_DELAY) if retry_after else None
                except (TypeError, ValueError):
                    delay = None
                delay = delay or min(_RETRY_BASE_DELAY * (2 ** attempt), _RETRY_MAX_DELAY)
                logger.warning("Wikidata rate limited; backing off %.1fs", delay)
                time.sleep(delay)
                continue
            logger.warning("Wikidata HTTP %s for %s", e.code, url)
            return None
        except Exception as e:  # other network / decode errors are non-fatal
            logger.warning("Wikidata request failed for %s: %s", url, e)
            return None
    return None


def search_entities(text: str, lang: str | None = None, limit: int = 5) -> list[Candidate]:
    """Query Wikidata `wbsearchentities` and return candidates."""
    params = {
        "action": "wbsearchentities",
        "search": text,
        "format": "json",
        "limit": limit,
    }
    if lang:
        params["language"] = lang
    url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
    data = _wikidata_request(url)
    if not data:
        return []

    out: list[Candidate] = []
    for item in data.get("search", []):
        out.append(
            Candidate(
                qid=item["id"],
                label=item.get("label", ""),
                description=item.get("description", ""),
                aliases=item.get("aliases", []) or [],
            )
        )
    return out


def _score(node_norm: str, label: str | None, cand: Candidate) -> float:
    score = 0.0
    cand_norm = normalize_entity(cand.label)
    if cand_norm == node_norm:
        score += 2.0
    if any(normalize_entity(a) == node_norm for a in cand.aliases):
        score += 1.5
    # Partial credit for a strong substring/alias overlap.
    if node_norm and (node_norm in cand_norm or cand_norm in node_norm):
        score += 0.5

    hints = _TYPE_HINTS.get(label or "")
    if hints and cand.description:
        desc = cand.description.lower()
        if any(h in desc for h in hints):
            score += 0.5
    return score


def disambiguate(
    node_text: str, label: str | None, candidates: list[Candidate]
) -> Candidate | None:
    """Pick the best-matching candidate, or `None` if none clears the threshold."""
    if not candidates:
        return None
    node_norm = normalize_entity(node_text)
    best, best_score = None, 0.0
    for cand in candidates:
        s = _score(node_norm, label, cand)
        if s > best_score:
            best, best_score = cand, s
    if best and best_score >= MATCH_THRESHOLD:
        return best
    return None


def link_entity(
    node_text: str, label: str | None, lang: str | None = None
) -> dict | None:
    """Resolve an entity to Wikidata.

    Returns `{"wikidata_id", "description", "external_ids"}` or `None`.
    """
    candidates = search_entities(node_text, lang=lang)
    best = disambiguate(node_text, label, candidates)
    if not best:
        return None
    return {
        "wikidata_id": best.qid,
        "description": best.description or None,
        "external_ids": {
            "wikidata": best.qid,
            "wikidata_url": f"https://www.wikidata.org/wiki/{best.qid}",
        },
    }
