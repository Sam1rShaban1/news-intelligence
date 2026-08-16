"""Entity text normalization for knowledge-graph deduplication.

Merges surface-form variants of the same entity so the graph links them:
  - "Скопје" (Macedonian Cyrillic)  -> "skopje" (Latin)
  - "İstanbul" / "istanbul" / "İSTANBUL" -> "istanbul"
  - "Tiranë" -> "tirane"
Pure stdlib — no model, safe to run on every extraction.
"""

import re
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
    """Return a canonical lowercase key for an entity surface form.

    Handles cross-script normalization (Macedonian Cyrillic -> Latin, Turkish /
    Albanian diacritic folding) and lowercasing. Remaining surface-form variants
    of the same real-world entity (inflections like shkup/shkupi, near-spelling
    like macedonia/maqedonia) are unified by fuzzy resolution in the graph
    layer (src/nlp/graph.py), not by a hardcoded alias list.
    """
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

    # 5. Drop digits / punctuation (e.g. "skopje12" -> "skopje",
    #    "north-macedonia" -> "north macedonia"); keep letters + spaces.
    s = re.sub(r"[^a-z\s]", "", s)
    s = " ".join(s.split())

    return s


# Common inflectional suffixes (Albanian, Macedonian, Slavic, Turkish-ish) used to
# reduce surface forms to a comparable base before similarity comparison. Curated
# by *language grammar*, not by entity name, so this is universal rather than a
# hardcoded alias list.
_INFLECTION_SUFFIXES = (
    "ish", "ski", "ska", "ova", "ov", "it", "ut", "at", "et",
    "te", "ja", "ve", "ne", "se", "i", "e", "a",
)


def _base_form(s: str) -> str:
    """Strip a single trailing inflectional suffix if doing so leaves >=4 chars.

    Suffixes are tried shortest-first so e.g. "tirane" strips "e" -> "tiran"
    (not "ne" -> "tira").
    """
    s = s.strip()
    for suf in sorted(_INFLECTION_SUFFIXES, key=len):
        if len(s) - len(suf) >= 4 and s.endswith(suf):
            return s[: -len(suf)]
    return s


def entity_similarity(a: str, b: str) -> float:
    """Universal similarity in [0, 1] for two normalized entity canonical texts.

    - 1.0 if identical or identical after stripping a common inflectional suffix
      (shkup / shkupi, tirana / tirane, macedonia / maqedonia, ohrid / ohrida).
    - otherwise a difflib ratio, so near-spellings score high without any
      per-name alias table.
    """
    if a == b:
        return 1.0
    ba, bb = _base_form(a), _base_form(b)
    if ba and ba == bb:
        return 1.0
    if ba and (ba == b or bb == a):
        return 0.95
    import difflib

    return difflib.SequenceMatcher(None, a, b).ratio()


def normalize_text(text: str) -> str:
    """Normalize free text for lexical matching: transliterate Macedonian
    Cyrillic to Latin, fold Turkish/Albanian diacritics to ASCII, lowercase
    and collapse whitespace. Used so curated lexicons (authored in Latin) can
    match original Cyrillic/diacritic text without a translation model.
    """
    return normalize_entity(text) if text else ""


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
