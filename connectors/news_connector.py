"""
Serper news connector.

Discovers fresh news article URLs per category through the Serper Google News API and
exposes them either as a one-shot fetch or as an endless async stream.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from config import Config
from utils import utcnow_iso

logger = logging.getLogger(__name__)


class MissingAPIKeyError(RuntimeError):
    """Raised when a required third-party API key is not configured."""


@dataclass
class NewsSearchResult:
    """A single news search hit."""

    url: str
    title: str
    snippet: str
    source: str
    date: str | None
    category: str
    search_query: str
    fetched_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SerperNewsConnector:
    """Fetches news URLs from Serper and de-duplicates them across calls."""

    def __init__(
        self,
        api_key: str | None = None,
        categories: list[str] | None = None,
        fetch_interval_seconds: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_key = api_key or Config.SERPER_API_KEY
        self.categories = categories or Config.NEWS_CATEGORIES
        self.fetch_interval = fetch_interval_seconds or Config.NEWS_FETCH_INTERVAL_SECONDS
        self.base_url = Config.SERPER_NEWS_URL
        self._transport = transport
        self._seen_urls: set[str] = set()
        self._running = False

    def _require_key(self) -> str:
        if not self.api_key:
            raise MissingAPIKeyError("SERPER_API_KEY is not configured")
        return self.api_key

    def parse_results(self, data: dict[str, Any], category: str, query: str) -> list[NewsSearchResult]:
        """Convert a Serper response payload into unseen results."""
        results: list[NewsSearchResult] = []
        for item in data.get("news", []):
            url = item.get("link") or ""
            if not url or url in self._seen_urls:
                continue
            self._seen_urls.add(url)
            results.append(
                NewsSearchResult(
                    url=url,
                    title=item.get("title", ""),
                    snippet=item.get("snippet", ""),
                    source=item.get("source", ""),
                    date=item.get("date"),
                    category=category,
                    search_query=query,
                    fetched_at=utcnow_iso(),
                )
            )
        return results

    async def search_news(
        self,
        query: str,
        num_results: int = 10,
        time_period: str = "d",
        category: str | None = None,
    ) -> list[NewsSearchResult]:
        """
        Search Serper for news.

        Args:
            query: Search query.
            num_results: Number of results requested from Serper.
            time_period: ``d`` (day), ``w`` (week) or ``m`` (month).
            category: Category label stored on results; defaults to ``query``.

        Raises:
            MissingAPIKeyError: if no Serper key is configured.
        """
        headers = {"X-API-KEY": self._require_key(), "Content-Type": "application/json"}
        payload = {"q": query, "num": num_results, "tbs": f"qdr:{time_period}"}

        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=30.0) as client:
                response = await client.post(self.base_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.error("Serper request failed for %r: %s", query, exc)
            return []

        results = self.parse_results(data, category=category or query, query=query)
        logger.info("Serper returned %d new items for %r", len(results), query)
        return results

    async def search_category(self, category: str, num_results: int | None = None) -> list[NewsSearchResult]:
        return await self.search_news(
            query=f"{category} news",
            num_results=num_results or Config.NEWS_RESULTS_PER_CATEGORY,
            category=category,
        )

    async def fetch_all_categories(self) -> list[NewsSearchResult]:
        """Fetch the latest news for every configured category."""
        all_results: list[NewsSearchResult] = []
        for category in self.categories:
            all_results.extend(await self.search_category(category))
            await asyncio.sleep(0.5)  # be gentle with the rate limit
        logger.info("Discovered %d new articles across categories", len(all_results))
        return all_results

    async def stream_news(self) -> AsyncGenerator[NewsSearchResult, None]:
        """Yield new results forever, polling every ``fetch_interval`` seconds."""
        self._running = True
        logger.info("Starting news stream for %d categories (every %ss)", len(self.categories), self.fetch_interval)
        while self._running:
            try:
                for result in await self.fetch_all_categories():
                    yield result
                await asyncio.sleep(self.fetch_interval)
            except asyncio.CancelledError:
                break
            except MissingAPIKeyError:
                raise
            except Exception:
                logger.exception("Error in news stream; retrying in 30s")
                await asyncio.sleep(30)

    def stop(self) -> None:
        self._running = False

    def get_stats(self) -> dict[str, Any]:
        return {
            "categories": self.categories,
            "fetch_interval_seconds": self.fetch_interval,
            "total_urls_seen": len(self._seen_urls),
            "is_running": self._running,
            "configured": bool(self.api_key),
        }
