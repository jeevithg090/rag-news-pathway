"""
User profile management.

Tracks interactions (view, chat, compare, like, share) and turns them into per-category and
per-topic affinity scores in ``[0, 1]`` that drive the personalised feed.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from config import Config
from utils import parse_topics, utcnow_iso

logger = logging.getLogger(__name__)

BASE_SCORE = 0.5
MIN_SCORE = 0.1
INTERACTION_WEIGHTS: dict[str, float] = {
    "view": 1.0,
    "chat": 2.0,
    "compare": 1.5,
    "like": 3.0,
    "share": 2.5,
}
INTERACTION_TYPES = tuple(INTERACTION_WEIGHTS)


@dataclass
class UserProfile:
    user_id: str
    created_at: str = field(default_factory=utcnow_iso)
    last_active: str = field(default_factory=utcnow_iso)
    category_preferences: dict[str, float] = field(default_factory=dict)
    topic_preferences: dict[str, float] = field(default_factory=dict)
    viewed_articles: list[str] = field(default_factory=list)
    chatted_articles: list[str] = field(default_factory=list)
    compared_articles: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def _top(prefs: dict[str, float], n: int) -> list[str]:
        return [key for key, _ in sorted(prefs.items(), key=lambda kv: kv[1], reverse=True)[:n]]

    def get_top_categories(self, n: int = 5) -> list[str]:
        return self._top(self.category_preferences, n)

    def get_top_topics(self, n: int = 10) -> list[str]:
        return self._top(self.topic_preferences, n)


class UserProfileManager:
    """In-memory store of user profiles."""

    def __init__(self, score_increment: float | None = None, decay_factor: float | None = None):
        self.score_increment = score_increment if score_increment is not None else Config.PREFERENCE_SCORE_INCREMENT
        self.decay_factor = decay_factor if decay_factor is not None else Config.PREFERENCE_DECAY_FACTOR
        self._users: dict[str, UserProfile] = {}

    def get_or_create_user(self, user_id: str) -> UserProfile:
        if user_id not in self._users:
            self._users[user_id] = UserProfile(user_id=user_id)
        return self._users[user_id]

    def get_user(self, user_id: str) -> UserProfile | None:
        return self._users.get(user_id)

    def _bump(self, preferences: dict[str, float], key: str, weight: float) -> float:
        new_score = min(1.0, preferences.get(key, BASE_SCORE) + self.score_increment * weight)
        preferences[key] = round(new_score, 6)
        return preferences[key]

    def seed_preferences(self, user_id: str, categories: list[str], boost: float = 0.3) -> UserProfile:
        """Give explicitly chosen categories (e.g. from onboarding) a head start."""
        user = self.get_or_create_user(user_id)
        for category in categories:
            current = user.category_preferences.get(category, BASE_SCORE)
            user.category_preferences[category] = max(current, min(1.0, BASE_SCORE + boost))
        return user

    def track_interaction(self, user_id: str, article: dict[str, Any], interaction_type: str) -> dict[str, Any]:
        """Record an interaction and update preferences; returns the changes made."""
        if interaction_type not in INTERACTION_WEIGHTS:
            raise ValueError(f"Unknown interaction type: {interaction_type!r}")

        user = self.get_or_create_user(user_id)
        user.last_active = utcnow_iso()

        weight = INTERACTION_WEIGHTS[interaction_type]
        article_id = article.get("article_id", "")
        category = article.get("category", "")
        updates: list[dict[str, Any]] = []

        if category:
            score = self._bump(user.category_preferences, category, weight)
            updates.append({"type": "category", "value": category, "new_score": score})

        for topic in parse_topics(article.get("topics")):
            # Topics move at half the rate of categories.
            score = self._bump(user.topic_preferences, topic, weight * 0.5)
            updates.append({"type": "topic", "value": topic, "new_score": score})

        if interaction_type == "view" and article_id not in user.viewed_articles:
            user.viewed_articles.append(article_id)
        elif interaction_type == "chat" and article_id not in user.chatted_articles:
            user.chatted_articles.append(article_id)

        return {
            "user_id": user_id,
            "article_id": article_id,
            "interaction_type": interaction_type,
            "preference_updates": updates,
        }

    def track_comparison(self, user_id: str, articles: list[dict[str, Any]]) -> dict[str, Any]:
        user = self.get_or_create_user(user_id)
        article_ids = [a.get("article_id", "") for a in articles]
        user.compared_articles.append(article_ids)

        updates: list[dict[str, Any]] = []
        for article in articles:
            updates.extend(self.track_interaction(user_id, article, "compare")["preference_updates"])
        return {"user_id": user_id, "compared_articles": article_ids, "preference_updates": updates}

    def apply_decay(self, user_id: str) -> None:
        """Decay all of a user's preferences towards ``MIN_SCORE``."""
        user = self.get_user(user_id)
        if not user:
            return
        for prefs in (user.category_preferences, user.topic_preferences):
            for key, value in prefs.items():
                prefs[key] = max(MIN_SCORE, value * self.decay_factor)

    def get_user_preferences_summary(self, user_id: str) -> dict[str, Any] | None:
        user = self.get_user(user_id)
        if not user:
            return None
        return {
            "user_id": user_id,
            "top_categories": user.get_top_categories(5),
            "top_topics": user.get_top_topics(10),
            "total_views": len(user.viewed_articles),
            "total_chats": len(user.chatted_articles),
            "total_comparisons": len(user.compared_articles),
            "last_active": user.last_active,
        }

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_users": len(self._users),
            "score_increment": self.score_increment,
            "decay_factor": self.decay_factor,
        }
