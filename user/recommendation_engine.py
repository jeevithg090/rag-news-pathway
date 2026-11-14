"""
Recommendation engine.

Ranks articles for a user from their preference scores, finds related articles by topic
overlap, and suggests head-to-head comparisons (e.g. Tesla vs BMW).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from rag.article_store import ArticleStore
from user.user_profile import BASE_SCORE, UserProfileManager
from utils import parse_datetime, utcnow

logger = logging.getLogger(__name__)

_ONE_DAY = timedelta(hours=24)

# Pairs of topic groups worth comparing against each other.
COMPARISON_PAIRS: list[tuple[list[str], list[str]]] = [
    (["Tesla"], ["BMW", "Mercedes", "Ford", "Toyota"]),
    (["Apple", "iPhone"], ["Samsung", "Google"]),
    (["Microsoft"], ["Apple", "Google"]),
    (["Amazon"], ["Google", "Microsoft"]),
    (["bitcoin", "crypto"], ["stock", "bank"]),
]


@dataclass
class ArticleRecommendation:
    article_id: str
    title: str
    score: float
    reasons: list[str]
    category: str
    topics: list[str]
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComparisonSuggestion:
    article_ids: list[str]
    titles: list[str]
    common_topics: list[str]
    comparison_prompt: str


def _lower(items: list[str]) -> set[str]:
    return {item.lower() for item in items}


class RecommendationEngine:
    def __init__(self, store: ArticleStore, profile_manager: UserProfileManager):
        self.store = store
        self.profile_manager = profile_manager

    def score_article(
        self, article: dict[str, Any], user_id: str, now: datetime | None = None
    ) -> tuple[float, list[str]]:
        """Score an article in ``[0, 1]`` for a user and explain why."""
        user = self.profile_manager.get_user(user_id)
        if not user:
            return BASE_SCORE, []

        score = BASE_SCORE
        reasons: list[str] = []

        category = article.get("category", "")
        cat_pref = user.category_preferences.get(category, BASE_SCORE)
        if cat_pref > 0.6:
            score += (cat_pref - BASE_SCORE) * 0.5
            reasons.append(f"Interested in {category}")

        matched = [t for t in article.get("topics", []) if user.topic_preferences.get(t, 0) > BASE_SCORE]
        if matched:
            score += min(sum(user.topic_preferences[t] * 0.1 for t in matched), 0.3)
            reasons.append(f"Matches interests: {', '.join(matched[:3])}")

        published = parse_datetime(article.get("publish_date"))
        if published and (now or utcnow()) - published < _ONE_DAY:
            score += 0.1
            reasons.append("Fresh news")

        if article.get("article_id") in user.viewed_articles:
            score -= 0.2
            reasons.append("Already viewed")

        return round(min(1.0, max(0.0, score)), 4), reasons

    def get_personalized_feed(
        self, user_id: str, limit: int = 20, exclude_viewed: bool = True
    ) -> list[ArticleRecommendation]:
        user = self.profile_manager.get_or_create_user(user_id)
        recommendations = []
        for article in self.store.all():
            if exclude_viewed and article["article_id"] in user.viewed_articles:
                continue
            score, reasons = self.score_article(article, user_id)
            recommendations.append(
                ArticleRecommendation(
                    article_id=article["article_id"],
                    title=article.get("title") or "Untitled",
                    score=score,
                    reasons=reasons,
                    category=article.get("category", ""),
                    topics=article.get("topics", []),
                    source=article.get("source", ""),
                )
            )
        # Stable sort keeps newest-first among equal scores.
        recommendations.sort(key=lambda rec: rec.score, reverse=True)
        return recommendations[:limit]

    def get_related_articles(self, article_id: str, limit: int = 5) -> list[ArticleRecommendation]:
        source = self.store.get(article_id)
        if not source:
            return []
        source_topics = _lower(source.get("topics", []))
        source_category = (source.get("category") or "").lower()

        related = []
        for article in self.store.all():
            if article["article_id"] == article_id:
                continue
            common = source_topics & _lower(article.get("topics", []))
            same_category = bool(source_category) and (article.get("category") or "").lower() == source_category
            score = len(common) * 0.3 + (0.2 if same_category else 0.0)
            if score <= 0:
                continue
            reasons = []
            if common:
                reasons.append(f"Common topics: {', '.join(sorted(common)[:3])}")
            if same_category:
                reasons.append(f"Same category: {source.get('category')}")
            related.append(
                ArticleRecommendation(
                    article_id=article["article_id"],
                    title=article.get("title") or "Untitled",
                    score=round(score, 4),
                    reasons=reasons,
                    category=article.get("category", ""),
                    topics=article.get("topics", []),
                    source=article.get("source", ""),
                )
            )
        related.sort(key=lambda rec: rec.score, reverse=True)
        return related[:limit]

    def suggest_comparison(self, article_id: str) -> ComparisonSuggestion | None:
        """If the article mentions one side of a known rivalry, find an article about the other."""
        source = self.store.get(article_id)
        if not source:
            return None
        source_topics = _lower(source.get("topics", []))

        targets: set[str] = set()
        for group_a, group_b in COMPARISON_PAIRS:
            if source_topics & _lower(group_a):
                targets = _lower(group_b)
                break
            if source_topics & _lower(group_b):
                targets = _lower(group_a)
                break
        if not targets:
            return None

        for article in self.store.all():
            if article["article_id"] == article_id:
                continue
            topics = _lower(article.get("topics", []))
            if topics & targets:
                return ComparisonSuggestion(
                    article_ids=[article_id, article["article_id"]],
                    titles=[source.get("title", ""), article.get("title", "")],
                    common_topics=sorted(source_topics & topics),
                    comparison_prompt="Compare how these two articles cover related topics.",
                )
        return None

    def get_stats(self) -> dict[str, Any]:
        return {"total_articles": len(self.store), "comparison_pairs": len(COMPARISON_PAIRS)}
