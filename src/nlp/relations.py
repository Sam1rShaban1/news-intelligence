"""relationship extraction — typed subject→predicate→object triples.

Phase 3c of the knowledge graph. Unlike `entity_edges` (which captures every
co-occurrence for network viz), `relationships` stores only *typed* triples where
a relation keyword was detected between two entities in the same sentence
e.g. "X appointed Y" -> (X, appointed, Y). Lightweight, no extra model — safe
for the Pi CPU. Predicate detection currently targets English cue phrases; for
non-English text it gracefully degrades to no typed triple (the co-occurrence
edge still captures the connection).
"""

import logging
import re
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.db.models.entity import Entity
from src.db.models.entity_node import EntityNode
from src.db.models.relationship import Relationship
from src.nlp.normalize import normalize_entity

logger = logging.getLogger(__name__)


# English cue-phrase -> normalized predicate.
RELATION_LEXICON: dict[str, str] = {
    "appointed": "appointed",
    "named": "appointed",
    "elected": "elected",
    "chose": "appointed",
    "selected": "appointed",
    "leads": "leads",
    "heads": "leads",
    "directs": "leads",
    "runs": "leads",
    "manages": "leads",
    "founded": "founded",
    "established": "founded",
    "created": "founded",
    "launched": "founded",
    "started": "founded",
    "born in": "born_in",
    "native of": "born_in",
    "from": "from",
    "located in": "located_in",
    "situated": "located_in",
    "based in": "located_in",
    "capital of": "located_in",
    "said": "stated",
    "stated": "stated",
    "announced": "stated",
    "declared": "stated",
    "reported": "stated",
    "owns": "owns",
    "acquired": "owns",
    "bought": "owns",
    "purchased": "owns",
    "supports": "supports",
    "backed": "supports",
    "endorsed": "supports",
    "criticized": "criticized",
    "attacked": "criticized",
    "condemned": "criticized",
    "met with": "met_with",
    "meeting with": "met_with",
    "talks with": "met_with",
    "signed": "signed",
    "agreed": "signed",
    "won": "won",
    "defeated": "won",
    "married": "married",
}

# Longest phrases first so "meeting with" wins over "with".
_SORTED_PHRASES = sorted(RELATION_LEXICON.keys(), key=len, reverse=True)
_PHRASE_RE = re.compile("|".join(re.escape(p) for p in _SORTED_PHRASES), re.IGNORECASE)


def split_sentences(text: str) -> list[str]:
    """Cheap sentence segmentation (no model)."""
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]


def detect_predicate(between_text: str) -> str | None:
    """Return a normalized predicate if a cue phrase is found, else None."""
    m = _PHRASE_RE.search(between_text or "")
    if not m:
        return None
    return RELATION_LEXICON[m.group(0).lower()]


def _node_id(session, canonical: str, label: str) -> int | None:
    node = session.execute(
        select(EntityNode.id).where(
            EntityNode.canonical_text == canonical, EntityNode.label == label
        )
    ).scalar()
    return node


def build_relationships(session, article_id: int, raw_entities: list[dict], text: str) -> int:
    """
    Extract typed triples from `raw_entities` using sentence context.

    For each sentence, entities whose span falls inside it are paired; if a
    relation cue phrase appears between the two entities, a `Relationship` row
    is stored (subject = earlier entity, object = later entity).

    Returns the number of typed triples created.
    """
    # Map each raw entity to (node_id, start, end, confidence) using the nodes
    # already created by build_article_graph.
    mentions = []
    for ent in raw_entities:
        t = (ent.get("text") or "").strip()
        label = (ent.get("label") or "MISC").upper()
        if not t:
            continue
        canonical = normalize_entity(t, label)
        nid = _node_id(session, canonical, label)
        if not nid:
            continue
        mentions.append(
            {
                "node_id": nid,
                "start": ent.get("start"),
                "end": ent.get("end"),
                "conf": ent.get("confidence") or 0.0,
            }
        )

    sentences = split_sentences(text)
    created = 0

    for sent in sentences:
        s_start = text.find(sent)
        if s_start < 0:
            s_start = 0
        s_end = s_start + len(sent)

        in_sent = [
            m for m in mentions if m["start"] is not None and s_start <= m["start"] < s_end
        ]
        in_sent.sort(key=lambda m: m["start"] or 0)

        for a, b in combinations(in_sent, 2):
            a_end = a["end"] if a["end"] is not None else (a["start"] or 0)
            b_start = b["start"] if b["start"] is not None else 0
            if b_start < a_end:
                continue  # overlapping/unordered spans
            between = text[a_end:b_start]
            predicate = detect_predicate(between)
            if not predicate:
                continue

            conf = round(min(a["conf"], b["conf"], 1.0) * 0.8, 3)
            stmt = pg_insert(Relationship).values(
                subject_node_id=a["node_id"],
                object_node_id=b["node_id"],
                predicate=predicate,
                article_id=article_id,
                confidence=conf,
                method="keyword",
            )
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["subject_node_id", "object_node_id", "predicate", "article_id"]
            )
            session.execute(stmt)
            created += 1

    session.commit()
    return created
