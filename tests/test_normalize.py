"""Tests for entity normalization (knowledge-graph dedup)."""

from src.nlp.normalize import normalize_entities, normalize_entity


def test_macedonian_cyrillic_folds_to_latin():
    assert normalize_entity("Скопје") == "skopje"
    assert normalize_entity("Македонија") == "makedonija"


def test_turkish_dotless_i():
    assert normalize_entity("İstanbul") == "istanbul"
    assert normalize_entity("TİRAN") == "tiran"
    assert normalize_entity("Türkiye") == "turkiye"


def test_albanian_e():
    assert normalize_entity("Tiranë") == "tirane"
    assert normalize_entity("Shkup") == "shkup"


def test_whitespace_and_case():
    assert normalize_entity("  Skopje  ") == "skopje"
    assert normalize_entity("SKOPJE") == "skopje"


def test_empty():
    assert normalize_entity("") == ""


def test_normalize_entities_attaches_key():
    out = normalize_entities([{"text": "Скопје", "label": "LOC"}])
    assert out[0]["normalized"] == "skopje"
