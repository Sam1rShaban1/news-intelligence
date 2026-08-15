"""Sentiment analysis.

English text uses VADER. Macedonian (mk), Albanian (sq) and Turkish (tr) use a
curated lexicon (Phase 4) run on the normalized (transliterated, diacritic-folded)
text — no heavy transformer, safe for the Pi CPU.
"""

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from src.nlp.lexicon import lexicon_sentiment
from src.nlp.normalize import normalize_text

_analyzer = SentimentIntensityAnalyzer()

# Languages covered by the curated lexicon rather than VADER.
LEXICON_LANGS = {"mk", "sq", "tr"}


def analyze_sentiment(text: str, lang: str | None = "en") -> dict:
    """
    Analyze sentiment of text.
    Returns dict with 'score' (float -1..+1), 'label' (pos/neg/neutral) and
    'method' ('vader' | 'lexicon').
    """
    if not text or not text.strip():
        return {"score": 0.0, "label": "neutral", "method": "none"}

    if lang in LEXICON_LANGS:
        score, label, hits = lexicon_sentiment(normalize_text(text), lang)
        return {"score": score, "label": label, "method": "lexicon", "hits": hits}

    scores = _analyzer.polarity_scores(text)
    compound = scores["compound"]

    if compound >= 0.05:
        label = "pos"
    elif compound <= -0.05:
        label = "neg"
    else:
        label = "neutral"

    return {"score": compound, "label": label, "method": "vader"}
