"""Tests for multilingual ONNX sentiment integration + lexicon/VADER fallback."""

from src.nlp.sentiment import analyze_sentiment
from src.nlp.sentiment_onnx import transformer_sentiment


def test_transformer_missing_returns_none():
    # No ONNX model baked in -> transformer path is a no-op (None) and callers fall back.
    assert transformer_sentiment("anything at all") is None


def test_mk_falls_back_to_lexicon():
    r = analyze_sentiment("Криза и корупција", "mk")
    assert r["label"] == "neg"
    assert r["method"] in ("lexicon", "transformer")


def test_en_uses_vader():
    r = analyze_sentiment("This is a wonderful and excellent development.", "en")
    assert r["label"] == "pos"
    assert r["score"] > 0


def test_empty_is_neutral():
    assert analyze_sentiment("", "en")["label"] == "neutral"
