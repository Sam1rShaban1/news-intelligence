"""Tests for script-based language detection (MK/SQ/TR/EN)."""

from src.workers.extract import detect_language


def test_macedonian_cyrillic():
    assert detect_language("Ова е текст на македонски јазик") == "mk"


def test_turkish():
    assert detect_language("Bu bir Türkçe metin örneğidir") == "tr"


def test_albanian():
    assert detect_language("Kjo është një tekst shqip") == "sq"


def test_english_default():
    assert detect_language("This is an English article about politics") == "en"


def test_empty_defaults_english():
    assert detect_language("") == "en"
