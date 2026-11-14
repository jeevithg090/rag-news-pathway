import pytest

from user.user_profile import BASE_SCORE, MIN_SCORE, UserProfileManager

ARTICLE = {"article_id": "a1", "category": "Technology", "topics": ["Tesla", "EV"]}


def test_view_updates_category_and_topics(profiles):
    changes = profiles.track_interaction("u1", ARTICLE, "view")
    user = profiles.get_user("u1")
    assert user.category_preferences["Technology"] == pytest.approx(BASE_SCORE + 0.1)
    assert user.topic_preferences["Tesla"] == pytest.approx(BASE_SCORE + 0.05)
    assert user.viewed_articles == ["a1"]
    assert {u["type"] for u in changes["preference_updates"]} == {"category", "topic"}


def test_weights_and_cap(profiles):
    for _ in range(10):
        profiles.track_interaction("u1", ARTICLE, "like")
    assert profiles.get_user("u1").category_preferences["Technology"] == 1.0


def test_unknown_interaction_rejected(profiles):
    with pytest.raises(ValueError):
        profiles.track_interaction("u1", ARTICLE, "stare")


def test_repeat_views_are_not_duplicated(profiles):
    profiles.track_interaction("u1", ARTICLE, "view")
    profiles.track_interaction("u1", ARTICLE, "view")
    assert profiles.get_user("u1").viewed_articles == ["a1"]


def test_comparison_tracks_all_articles(profiles):
    other = {"article_id": "a2", "category": "Business", "topics": []}
    result = profiles.track_comparison("u1", [ARTICLE, other])
    assert result["compared_articles"] == ["a1", "a2"]
    assert set(profiles.get_user("u1").category_preferences) == {"Technology", "Business"}


def test_decay_floors_at_minimum(profiles):
    profiles.track_interaction("u1", ARTICLE, "view")
    for _ in range(10):
        profiles.apply_decay("u1")
    assert profiles.get_user("u1").category_preferences["Technology"] == MIN_SCORE
    profiles.apply_decay("unknown")  # no-op


def test_seed_preferences_never_lowers_existing(profiles):
    for _ in range(5):
        profiles.track_interaction("u1", ARTICLE, "like")
    profiles.seed_preferences("u1", ["Technology", "Sports"])
    prefs = profiles.get_user("u1").category_preferences
    assert prefs["Technology"] == 1.0
    assert prefs["Sports"] == pytest.approx(0.8)


def test_summary_none_for_unknown_user():
    assert UserProfileManager().get_user_preferences_summary("ghost") is None
