"""Tests for VADER sentiment (English baseline)."""

from src.nlp.sentiment import analyze_sentiment


def test_positive():
    r = analyze_sentiment("This is a wonderful and excellent development, we are very happy.")
    assert r["label"] == "pos"
    assert r["score"] > 0


def test_negative():
    r = analyze_sentiment("Terrible disaster, horrible crime, we are devastated and angry.")
    assert r["label"] == "neg"
    assert r["score"] < 0


def test_neutral():
    r = analyze_sentiment("The committee will meet on Tuesday to discuss the budget.")
    assert r["label"] == "neutral"


def test_empty():
    assert analyze_sentiment("")["label"] == "neutral"
