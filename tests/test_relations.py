"""Tests for relationship extraction (sentence split + predicate detection)."""

from src.nlp.relations import detect_predicate, split_sentences


def test_split_sentences():
    sents = split_sentences("Skopje is the capital. It is in North Macedonia! Really?")
    assert len(sents) == 3
    assert sents[0].startswith("Skopje")
    assert sents[1].startswith("It is")


def test_detect_predicate_known():
    assert detect_predicate("The government appointed her as minister") == "appointed"
    assert detect_predicate("He was elected president") == "elected"
    assert detect_predicate("The company is located in Berlin") == "located_in"
    assert detect_predicate("They met with the delegation") == "met_with"


def test_detect_predicate_longest_phrase_wins():
    # "meeting with" should win over bare "with"
    assert detect_predicate("they held a meeting with the council") == "met_with"


def test_detect_predicate_none():
    assert detect_predicate("The weather was sunny today") is None
    assert detect_predicate("") is None


def test_detect_predicate_multilingual():
    # Macedonian Cyrillic cue phrase -> transliterated then matched
    assert detect_predicate("Тој изјави дека...") == "stated"
    # Turkish cue phrase (diacritic-folded)
    assert detect_predicate("Bakan açıkladı ki") == "stated"
    # Albanian cue phrase
    assert detect_predicate("ai deklaroi se") == "stated"
    # Macedonian 'located in'
    assert detect_predicate("Скопје се наоѓа во Македонија") == "located_in"
