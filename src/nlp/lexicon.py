"""Curated sentiment lexicons for non-English coverage (MK / SQ / TR).

Phase 4 — multilingual sentiment without a heavy transformer. The analyzer
falls back to VADER for English; for Macedonian (mk), Albanian (sq) and Turkish
(tr) it scores against these lexicons run on the *normalized* (transliterated,
diacritic-folded) text. This keeps the Pi CPU-free of large models.

Coverage is intentionally limited to high-signal news/politics vocabulary — it is
not a full sentiment model and will read as neutral for most general text. Words
are authored in their normalized (Latin, ASCII-folded) form so they match the
output of `normalize_text`.
"""

import re

SENTIMENT_LEXICON: dict[str, dict[str, float]] = {
    "mk": {
        # negative
        "ubien": -1.0, "ubiena": -1.0, "ubieni": -1.0, "ubistvo": -1.0,
        "kriza": -1.0, "napad": -1.0, "vojna": -1.0, "nasilie": -1.0,
        "nasilstvo": -1.0, "teror": -1.0, "korupcija": -1.0, "kriminal": -1.0,
        "beda": -1.0, "smrt": -1.0, "zaguba": -1.0, "propast": -1.0,
        "gubitok": -1.0, "zatvor": -1.0, "tenzii": -1.0, "konflikt": -1.0,
        "katastrofa": -1.0, "tragedija": -1.0, "protest": -0.5,
        "krizata": -1.0, "optuzba": -1.0, "skandal": -1.0,
        # positive
        "uspeh": 1.0, "rast": 1.0, "mir": 1.0, "pobeda": 1.0, "razvoj": 1.0,
        "podobruvanje": 1.0, "podkrepa": 1.0, "dobivka": 1.0, "stabilnost": 1.0,
        "napredok": 1.0, "srekja": 1.0, "ljubov": 1.0, "zdrave": 1.0,
        "obnova": 1.0, "investicija": 1.0, "dogovor": 1.0, "sozdadeno": 1.0,
    },
    "sq": {
        # negative
        "vrare": -1.0, "krim": -1.0, "luft": -1.0, "dhune": -1.0,
        "korrupsion": -1.0, "krize": -1.0, "sulm": -1.0, "vdekje": -1.0,
        "tragjedi": -1.0, "konflikt": -1.0, "terror": -1.0, "protest": -0.5,
        "faliment": -1.0, "varferi": -1.0, "denoncoi": -1.0, "kunder": -0.5,
        "skandal": -1.0, "kriz": -1.0,
        # positive
        "sukses": 1.0, "rritje": 1.0, "paqe": 1.0, "fitore": 1.0,
        "zhvillim": 1.0, "mireqenie": 1.0, "mbrojtje": 1.0, "investim": 1.0,
        "stabilite": 1.0, "progres": 1.0, "bashkepunim": 1.0, "lumturi": 1.0,
        "marreveshje": 1.0, "dobit": 1.0, "perparim": 1.0,
    },
    "tr": {
        # negative
        "olduruldu": -1.0, "cinayet": -1.0, "savas": -1.0, "siddet": -1.0,
        "yolsuzluk": -1.0, "kriz": -1.0, "saldiri": -1.0, "olum": -1.0,
        "trajedi": -1.0, "teror": -1.0, "protesto": -0.5, "iflas": -1.0,
        "yoksulluk": -1.0, "catisma": -1.0, "dusus": -1.0, "kotulesme": -1.0,
        "skandal": -1.0, "elestiri": -1.0,
        # positive
        "basari": 1.0, "artis": 1.0, "baris": 1.0, "zafer": 1.0,
        "kalkinma": 1.0, "ilerleme": 1.0, "yatirim": 1.0, "istikrar": 1.0,
        "refah": 1.0, "mutluluk": 1.0, "destek": 1.0, "iyilesme": 1.0,
        "anlasma": 1.0, "kazanim": 1.0, "isbirligi": 1.0,
    },
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def lexicon_sentiment(normalized_text: str, lang: str) -> tuple[float, str, int]:
    """
    Score normalized text against the lexicon for `lang`.

    Returns (score, label, hits):
      score  - squashed to [-1, 1] via raw / (|raw| + 2)
      label  - 'pos' / 'neg' / 'neutral'
      hits   - number of lexicon tokens matched
    """
    lex = SENTIMENT_LEXICON.get(lang)
    if not lex or not normalized_text:
        return 0.0, "neutral", 0

    tokens = _TOKEN_RE.findall(normalized_text)
    raw = 0.0
    hits = 0
    for tok in tokens:
        if tok in lex:
            raw += lex[tok]
            hits += 1

    if hits == 0:
        return 0.0, "neutral", 0

    score = raw / (abs(raw) + 2.0)
    if score >= 0.05:
        label = "pos"
    elif score <= -0.05:
        label = "neg"
    else:
        label = "neutral"
    return round(score, 3), label, hits
