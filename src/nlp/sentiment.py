"""Sentiment analysis using VADER."""

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()


def analyze_sentiment(text: str) -> dict:
    """
    Analyze sentiment of text.
    Returns dict with 'score' (float -1..+1) and 'label' (pos/neg/neutral).
    """
    if not text or not text.strip():
        return {"score": 0.0, "label": "neutral"}

    scores = _analyzer.polarity_scores(text)
    compound = scores["compound"]

    if compound >= 0.05:
        label = "pos"
    elif compound <= -0.05:
        label = "neg"
    else:
        label = "neutral"

    return {"score": compound, "label": label}
