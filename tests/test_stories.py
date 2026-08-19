"""Tests for story/event clustering (pure scoring logic)."""

from src.db.models.story import Story
from src.nlp.stories import score_match, select_story


def _story(ids):
    s = Story(title="x")
    s.entity_node_ids = ids
    return s


def test_score_match_disjoint():
    assert score_match({1, 2}, {3, 4}) == 0.0


def test_score_match_partial():
    # inter {2,3} / union {1,2,3,4} = 0.5
    assert score_match({1, 2, 3}, {2, 3, 4}) == 0.5


def test_select_story_above_threshold():
    a = {1, 2, 3}
    cands = [_story([2, 3, 4]), _story([5, 6])]
    best = select_story(a, cands, 0.3)
    assert best is not None
    assert best.entity_node_ids == [2, 3, 4]


def test_select_story_below_threshold():
    a = {1}
    cands = [_story([2, 3, 4, 5, 6, 7])]  # Jaccard 1/7 < 0.3
    assert select_story(a, cands, 0.3) is None


def test_select_story_single_shared_not_merged():
    # Jaccard is 0.5 (2 shared of 4 in union) but only ONE entity overlaps, so the
    # min-shared-entities gate must keep the articles as separate stories.
    a = {1, 2, 3}
    cands = [_story([3, 4, 5])]
    assert select_story(a, cands) is None


def test_select_story_two_shared_merged():
    # Jaccard 0.5 with two shared canonical entities clears both gates.
    a = {1, 2, 3}
    cands = [_story([2, 3, 4])]
    best = select_story(a, cands)
    assert best is not None
    assert best.entity_node_ids == [2, 3, 4]
