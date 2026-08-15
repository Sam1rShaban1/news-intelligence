"""Entity text normalization for knowledge-graph deduplication.

Merges surface-form variants of the same entity so the graph links them:
  - "Скопје" (Macedonian Cyrillic)  -> "skopje" (Latin)
  - "İstanbul" / "istanbul" / "İSTANBUL" -> "istanbul"
  - "Tiranë" -> "tirane"
Pure stdlib — no model, safe to run on every extraction.
"""

import unicodedata

# Macedonian Cyrillic -> Latin transliteration (official RNM transliteration).
_MK_CYRILLIC_TO_LATIN = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Ѓ": "Gj", "Е": "E",
    "Ж": "Zh", "З": "Z", "Ѕ": "Dz", "И": "I", "Ј": "J", "К": "K", "Л": "L",
    "Љ": "Lj", "М": "M", "Н": "N", "Њ": "Nj", "О": "O", "П": "P", "Р": "R",
    "С": "S", "Т": "T", "Ќ": "Kj", "У": "U", "Ф": "F", "Х": "H", "Ц": "C",
    "Ч": "Ch", "Џ": "Dj", "Ш": "Sh",
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ѓ": "gj", "е": "e",
    "ж": "zh", "з": "z", "ѕ": "dz", "и": "i", "ј": "j", "к": "k", "л": "l",
    "љ": "lj", "м": "m", "н": "n", "њ": "nj", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "ќ": "kj", "у": "u", "ф": "f", "х": "h", "ц": "c",
    "ч": "ch", "џ": "dj", "ш": "sh",
}

# Turkish / Albanian special characters -> ASCII fold.
_SPECIAL_FOLD = {
    "ı": "i", "İ": "i", "I": "i",  # dotless-i handled as i
    "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    "ë": "e", "Ë": "e", "ė": "e", "È": "e", "é": "e", "É": "e",
    "á": "a", "Á": "a", "í": "i", "Í": "i", "ó": "o", "Ó": "o", "ú": "u", "Ú": "u",
    "â": "a", "Â": "a", "î": "i", "Î": "i", "ș": "s", "Ș": "s", "ț": "t", "Ț": "t",
}


def normalize_entity(text: str, label: str | None = None) -> str:
    """Return a canonical lowercase key for an entity surface form."""
    if not text:
        return ""
    s = text.strip()

    # 1. Transliterate Macedonian Cyrillic -> Latin
    s = "".join(_MK_CYRILLIC_TO_LATIN.get(ch, ch) for ch in s)

    # 2. Fold Turkish / Albanian special characters -> ASCII
    s = "".join(_SPECIAL_FOLD.get(ch, ch) for ch in s)

    # 3. Unicode compatibility decomposition, strip combining marks (diacritics)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))

    # 4. Lowercase + collapse internal whitespace
    s = " ".join(s.lower().split())

    return s


def normalize_entities(
    entities: list[dict], label: str | None = None
) -> list[dict]:
    """Attach a `normalized` key to each entity dict in place-style (returns new list)."""
    out = []
    for ent in entities:
        e = dict(ent)
        e["normalized"] = normalize_entity(ent.get("text", ""), label or ent.get("label"))
        out.append(e)
    return out
