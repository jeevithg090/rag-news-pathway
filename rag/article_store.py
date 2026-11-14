"""
In-process article store with a lightweight keyword retriever.

The same store backs the news feed, recommendations and RAG retrieval so that every
component sees an article as soon as it is indexed.
"""

from __future__ import annotations

import threading
from collections import Counter
from typing import Any

from utils import parse_topics, tokenize


class ArticleStore:
    """Thread-safe, insertion-ordered dictionary of articles keyed by ``article_id``."""

    def __init__(self) -> None:
        self._articles: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def add(self, article: dict[str, Any]) -> bool:
        """Insert or replace an article. Returns ``True`` if it was new."""
        article_id = article.get("article_id")
        if not article_id:
            return False
        normalised = {**article, "topics": parse_topics(article.get("topics"))}
        with self._lock:
            is_new = article_id not in self._articles
            self._articles[article_id] = normalised
        return is_new

    def get(self, article_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._articles.get(article_id)

    def get_many(self, article_ids: list[str]) -> list[dict[str, Any]]:
        with self._lock:
            return [self._articles[aid] for aid in article_ids if aid in self._articles]

    def all(self, newest_first: bool = True) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._articles.values())
        return list(reversed(items)) if newest_first else items

    def __len__(self) -> int:
        with self._lock:
            return len(self._articles)

    def __contains__(self, article_id: object) -> bool:
        with self._lock:
            return article_id in self._articles

    def clear(self) -> None:
        with self._lock:
            self._articles.clear()

    def search(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
        article_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Rank articles by keyword overlap with ``query``.

        Title hits count double, topic hits count triple, body hits count once per distinct
        term (with a small bonus for frequency). Articles with zero score are dropped.
        """
        terms = set(tokenize(query))
        if not terms:
            return []
        allowed = set(article_ids) if article_ids else None
        category_lower = category.lower() if category else None

        scored: list[tuple[float, int, dict[str, Any]]] = []
        for order, doc in enumerate(self.all(newest_first=True)):
            if allowed is not None and doc["article_id"] not in allowed:
                continue
            if category_lower and (doc.get("category") or "").lower() != category_lower:
                continue

            title_tokens = set(tokenize(doc.get("title") or ""))
            topic_tokens = {tok for topic in doc.get("topics", []) for tok in tokenize(topic)}
            body_counts = Counter(tokenize(doc.get("content") or ""))

            score = 0.0
            for term in terms:
                if term in topic_tokens:
                    score += 3
                if term in title_tokens:
                    score += 2
                if body_counts.get(term):
                    score += 1 + min(body_counts[term], 10) * 0.05
            if score > 0:
                # ``order`` keeps newer articles first among ties.
                scored.append((score, -order, doc))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [doc for _, _, doc in scored[:top_k]]
