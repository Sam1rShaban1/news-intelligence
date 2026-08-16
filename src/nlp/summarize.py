"""Extractive summarization — lightweight, no model (Phase 7).

Splits an article into sentences and picks the most salient ones by lead
position + length, capping at `max_chars`. Runs in the extract worker (which
already has the article body), so no extra ML stage is needed.
"""

import re

_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    return [p.strip() for p in _SENT_SPLIT.split(text) if p and p.strip()]


def _scores(sentences: list[str]) -> list[tuple[float, int]]:
    n = len(sentences)
    out = []
    for i, s in enumerate(sentences):
        lead = 1.0 - (i / max(1, n))  # earlier sentences score higher
        length_bonus = 0.0 if 40 <= len(s) <= 220 else -0.4
        out.append((lead + length_bonus, i))
    return out


def extractive_summary(text: str, max_chars: int = 220) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return ""
    if sum(len(s) for s in sentences) <= max_chars:
        return " ".join(sentences)

    chosen: list[str] = []
    used = 0
    for _, idx in sorted(_scores(sentences), key=lambda x: (-x[0], x[1])):
        s = sentences[idx]
        if used and used + len(s) + 1 > max_chars:
            break
        chosen.append(s)
        used += len(s) + 1

    # restore original reading order
    chosen.sort(key=lambda s: sentences.index(s))
    return " ".join(chosen)
