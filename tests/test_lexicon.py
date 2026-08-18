"""Tests for multilingual sentiment (Phase 4 lexicon)."""

import os

import pytest

from config.settings import settings
from src.nlp.lexicon import lexicon_sentiment
from src.nlp.normalize import normalize_text
from src.nlp.sentiment import analyze_sentiment

# These tests exercise the lexicon / VADER fallback path, which is only taken when the
# ONNX model is absent. Skip them where the model is baked in (e.g. the CI image).
_ONNX_PRESENT = os.path.exists(settings.sentiment_model_path) and os.path.exists(
    os.path.join(os.path.dirname(settings.sentiment_model_path), "sentiment_tokenizer.json")
)
pytestmark = pytest.mark.skipif(
    _ONNX_PRESENT, reason="ONNX model present; fallback path not exercised"
)


def test_lexicon_mk_negative():
    # Macedonian Cyrillic -> should transliterate and score negative
    text = "Криза и корупција предизвикаа насилство."
    score, label, hits = lexicon_sentiment(normalize_text(text), "mk")
    assert hits >= 3
    assert label == "neg"
    assert score < 0


def test_lexicon_sq_positive():
    text = "Sukses dhe zhvillim i mirëqenie."
    score, label, hits = lexicon_sentiment(normalize_text(text), "sq")
    assert hits >= 3
    assert label == "pos"
    assert score > 0


def test_lexicon_tr_positive():
    text = "Başarı ve kalkınma getirdi refah."
    score, label, hits = lexicon_sentiment(normalize_text(text), "tr")
    assert hits >= 3
    assert label == "pos"


def test_analyze_sentiment_mk_uses_lexicon():
    res = analyze_sentiment("Криза и корупција.", "mk")
    assert res["method"] == "lexicon"
    assert res["label"] == "neg"


def test_analyze_sentiment_en_uses_vader():
    res = analyze_sentiment("This is a terrible disaster!", "en")
    assert res["method"] == "vader"
    assert res["label"] == "neg"


def test_analyze_sentiment_empty():
    res = analyze_sentiment("", "mk")
    assert res["label"] == "neutral"
