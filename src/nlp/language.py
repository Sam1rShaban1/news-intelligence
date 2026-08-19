"""Language detection — Macedonian / Albanian / Turkish / English.

High-precision script cues win first (Cyrillic -> Macedonian; Turkish/Albanian
diacritics -> tr/sq). For the remaining Latin-script text — including Albanian or
Turkish written without those diacritics, which a naive script-only detector
mislabels as English — a lightweight `langid` classifier resolves the language.
Unsupported classifier results fall back to English.
"""

import re

# Script-based language detection for MK/SQ/TR/EN
_RE_CYRILLIC = re.compile(r"[\u0400-\u04FF]")
# Turkish-specific: ğ, ş, ı (dotless i), İ (capital I with dot) — not found in
# Western European langs
_RE_TURKISH = re.compile(r"[ğışĞIŞ]")
_RE_ALBANIAN = re.compile(r"[ëË]")
# Extracted content can carry HTML; strip tags so they don't pollute detection.
_RE_TAG = re.compile(r"<[^>]+>")

# Languages we actively support; anything else falls back to English.
_SUPPORTED = {"mk", "sq", "tr", "en"}


def detect_language(text: str | None) -> str:
    """Return one of mk, sq, tr, en for the given text."""
    if not text:
        return "en"
    clean = _RE_TAG.sub(" ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return "en"
    if _RE_CYRILLIC.search(clean):
        return "mk"
    if _RE_TURKISH.search(clean):
        return "tr"
    if _RE_ALBANIAN.search(clean):
        return "sq"
    try:
        from langid import classify

        lang, _ = classify(clean)
    except Exception:  # langid unavailable — leave as English
        return "en"
    return lang if lang in _SUPPORTED else "en"
