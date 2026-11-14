"""
Article scraper built on news-please.

Extracts full article text and metadata from URLs. Extraction is blocking, so it runs in a
thread pool to keep the event loop responsive.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any

from utils import utcnow_iso

logger = logging.getLogger(__name__)

# Keywords used for lightweight topic tagging (feeds recommendations and comparisons).
TOPIC_KEYWORDS: tuple[str, ...] = (
    # Technology
    "AI", "artificial intelligence", "machine learning", "technology", "startup", "software",
    "cloud", "data", "Apple", "iPhone", "Google", "Microsoft", "Amazon", "Meta", "Samsung",
    # Finance
    "stock", "market", "investment", "finance", "economy", "bank", "crypto", "bitcoin",
    "trading", "earnings",
    # Automotive
    "Tesla", "EV", "electric vehicle", "automotive", "BMW", "Ford", "Toyota", "Mercedes",
    # Business
    "CEO", "merger", "acquisition", "IPO",
    # Other
    "health", "science", "research", "climate", "energy", "space",
)  # fmt: skip

MAX_TOPICS = 10


def generate_article_id(url: str) -> str:
    """Stable 16-hex-char identifier derived from the article URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def extract_topics(title: str, content: str, keywords: tuple[str, ...] = TOPIC_KEYWORDS) -> list[str]:
    """
    Return the keywords that appear in the article as whole words (case-insensitive).

    Order follows ``keywords`` so results are deterministic.
    """
    text = f"{title} {content}"
    topics: list[str] = []
    for keyword in keywords:
        if re.search(rf"(?<![\w]){re.escape(keyword)}(?![\w])", text, flags=re.IGNORECASE):
            topics.append(keyword)
            if len(topics) >= MAX_TOPICS:
                break
    return topics


@dataclass
class ArticleContent:
    """Extracted article content and metadata."""

    article_id: str
    url: str
    title: str
    content: str
    author: str | None = None
    publish_date: str | None = None
    source: str = ""
    category: str = ""
    description: str | None = None
    image_url: str | None = None
    language: str | None = None
    topics: list[str] = field(default_factory=list)
    scraped_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ArticleScraper:
    """Scrapes articles concurrently with a bounded thread pool and an in-memory cache."""

    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._cache: dict[str, ArticleContent] = {}

    def _scrape_article_sync(self, url: str, category: str = "", source: str = "") -> ArticleContent | None:
        try:
            from newsplease import NewsPlease

            article = NewsPlease.from_url(url, request_args={"timeout": 20}, fetch_images=False)
        except Exception as exc:  # news-please raises a wide variety of errors
            logger.warning("Failed to scrape %s: %s", url, exc)
            return None

        if article is None or not (article.title or article.maintext):
            logger.warning("No article content extracted from %s", url)
            return None

        title = article.title or ""
        content = article.maintext or ""
        publish_date = article.date_publish.isoformat() if article.date_publish else None

        return ArticleContent(
            article_id=generate_article_id(url),
            url=url,
            title=title,
            content=content,
            author=", ".join(article.authors) if article.authors else None,
            publish_date=publish_date,
            source=source or article.source_domain or "",
            category=category,
            description=article.description,
            image_url=article.image_url,
            language=article.language,
            topics=extract_topics(title, content),
        )

    async def scrape_article(self, url: str, category: str = "", source: str = "") -> ArticleContent | None:
        """Scrape a single article (cached by URL)."""
        article_id = generate_article_id(url)
        if article_id in self._cache:
            return self._cache[article_id]

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(self._executor, self._scrape_article_sync, url, category, source)
        if result:
            self._cache[article_id] = result
        return result

    async def scrape_articles(self, items: list[dict[str, str]], batch_size: int = 5) -> list[ArticleContent]:
        """Scrape many articles in batches; returns only successful extractions."""
        results: list[ArticleContent] = []
        for start in range(0, len(items), batch_size):
            batch = items[start : start + batch_size]
            scraped = await asyncio.gather(
                *(
                    self.scrape_article(item.get("url", ""), item.get("category", ""), item.get("source", ""))
                    for item in batch
                    if item.get("url")
                )
            )
            results.extend(article for article in scraped if article)
        logger.info("Scraped %d of %d articles", len(results), len(items))
        return results

    def get_stats(self) -> dict[str, Any]:
        return {"cached_articles": len(self._cache), "max_workers": self.max_workers}

    def clear_cache(self) -> None:
        self._cache.clear()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
