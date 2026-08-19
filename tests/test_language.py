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


def test_albanian_latin_without_e_trema():
    # Albanian written without the ë diaeresis (common) — the old script heuristic
    # defaulted this to English. langid recovers it.
    text = (
        "Kjo eshte nje lajm i ri nga qeveria qe tregon zhvillimet e fundit ne vend."
    )
    assert detect_language(text) == "sq"


def test_turkish_latin_without_special_chars():
    # Turkish without ğ/ş/ı/İ — with enough text langid resolves it (short samples
    # collide with Indonesian/Malay). The old detector defaulted this to English.
    text = (
        "Türkiye Cumhuriyeti hazineden sorumlu bakanlarin katilimiyla ekonomik "
        "reformlarin konusuldugu bir toplanti yapildi ve yeni kararlar alindi."
    )
    assert detect_language(text) == "tr"
