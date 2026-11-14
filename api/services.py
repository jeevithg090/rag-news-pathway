"""Wiring of the application's long-lived components and the news ingestion workflow."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from api.database import Database
from config import Config
from connectors.article_scraper import ArticleContent, ArticleScraper
from connectors.news_connector import NewsSearchResult, SerperNewsConnector
from connectors.youtube_analyzer import YouTubeAnalyzer
from rag.article_store import ArticleStore
from rag.rag_engine import RAGEngine
from user.recommendation_engine import RecommendationEngine
from user.user_profile import UserProfileManager

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks WebSocket clients per channel and broadcasts JSON messages to them."""

    def __init__(self) -> None:
        self.active: dict[str, set[WebSocket]] = {"feed": set(), "chat": set()}

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        await websocket.accept()
        self.active[channel].add(websocket)

    def disconnect(self, websocket: WebSocket, channel: str) -> None:
        self.active[channel].discard(websocket)

    async def broadcast(self, message: dict[str, Any], channel: str) -> None:
        for connection in list(self.active[channel]):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection, channel)


@dataclass
class Services:
    store: ArticleStore
    profiles: UserProfileManager
    recommendations: RecommendationEngine
    rag: RAGEngine
    news: SerperNewsConnector
    scraper: ArticleScraper
    youtube: YouTubeAnalyzer
    db: Database
    ws: ConnectionManager = field(default_factory=ConnectionManager)
    _ingest_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @classmethod
    def create(cls, database_url: str | None = None) -> Services:
        store = ArticleStore()
        profiles = UserProfileManager()
        return cls(
            store=store,
            profiles=profiles,
            recommendations=RecommendationEngine(store, profiles),
            rag=RAGEngine(store),
            news=SerperNewsConnector(),
            scraper=ArticleScraper(),
            youtube=YouTubeAnalyzer(),
            db=Database(database_url or Config.DATABASE_URL),
        )

    async def index_article(self, article: ArticleContent) -> bool:
        """Add a scraped article to the store and notify feed subscribers if it is new."""
        is_new = self.store.add(article.to_dict())
        if is_new:
            await self.ws.broadcast(
                {
                    "type": "new_article",
                    "article": {
                        "article_id": article.article_id,
                        "title": article.title,
                        "category": article.category,
                        "source": article.source,
                    },
                },
                "feed",
            )
        return is_new

    async def ingest(self, results: list[NewsSearchResult]) -> list[ArticleContent]:
        """Scrape search results and index the successfully extracted articles."""
        async with self._ingest_lock:
            articles = await self.scraper.scrape_articles(
                [{"url": r.url, "category": r.category, "source": r.source} for r in results]
            )
            for article in articles:
                await self.index_article(article)
            return articles

    async def stream_forever(self) -> None:
        """Background loop: poll Serper, scrape and index new articles."""
        try:
            async for result in self.news.stream_news():
                await self.ingest([result])
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("News streaming stopped")

    def shutdown(self) -> None:
        self.news.stop()
        self.scraper.shutdown()
        self.db.dispose()
