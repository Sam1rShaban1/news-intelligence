"""Tests for extractive summarization (Phase 7)."""

from src.nlp.summarize import extractive_summary, split_sentences


def test_split_sentences():
    s = split_sentences("Hello world. This is a test! Really?")
    assert len(s) == 3
    assert s[0].startswith("Hello")


def test_short_text_returns_all():
    t = "Short text here."
    assert extractive_summary(t) == t


def test_long_text_is_capped():
    text = ". ".join([f"Sentence number {i} about the event." for i in range(20)])
    out = extractive_summary(text, max_chars=120)
    assert len(out) <= 140


def test_order_preserved():
    text = "First sentence leads. Second sentence follows. Third trails."
    out = extractive_summary(text, max_chars=60)
    assert out.index("First") < out.index("Second")
