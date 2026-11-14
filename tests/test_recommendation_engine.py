from datetime import timedelta

from user.recommendation_engine import RecommendationEngine
from utils import utcnow


def test_feed_prefers_users_interests(store, profiles):
    engine = RecommendationEngine(store, profiles)
    profiles.seed_preferences("u1", ["Finance"])
    feed = engine.get_personalized_feed("u1")
    assert feed[0].article_id == "mkt001"
    assert "Interested in Finance" in feed[0].reasons


def test_feed_excludes_viewed_when_requested(store, profiles):
    engine = RecommendationEngine(store, profiles)
    profiles.track_interaction("u1", store.get("tesla001"), "view")
    assert "tesla001" not in [r.article_id for r in engine.get_personalized_feed("u1", exclude_viewed=True)]
    kept = {r.article_id: r for r in engine.get_personalized_feed("u1", exclude_viewed=False)}
    assert "Already viewed" in kept["tesla001"].reasons


def test_recency_bonus_handles_timezones(store, profiles):
    engine = RecommendationEngine(store, profiles)
    profiles.get_or_create_user("u1")
    fresh = {
        "article_id": "x",
        "category": "",
        "topics": [],
        "publish_date": (utcnow() - timedelta(hours=2)).isoformat(),
    }
    stale = {**fresh, "publish_date": (utcnow() - timedelta(days=3)).isoformat()}
    assert engine.score_article(fresh, "u1")[1] == ["Fresh news"]
    assert engine.score_article(stale, "u1")[1] == []


def test_related_articles_by_topic_overlap(store, profiles):
    engine = RecommendationEngine(store, profiles)
    related = engine.get_related_articles("tesla001")
    assert [r.article_id for r in related] == ["bmw001"]
    assert any("Common topics" in reason for reason in related[0].reasons)
    assert engine.get_related_articles("missing") == []


def test_comparison_suggestion_pairs_rivals(store, profiles):
    engine = RecommendationEngine(store, profiles)
    suggestion = engine.suggest_comparison("tesla001")
    assert suggestion.article_ids == ["tesla001", "bmw001"]
    assert "ev" in suggestion.common_topics
    assert engine.suggest_comparison("mkt001") is None
