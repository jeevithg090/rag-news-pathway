from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.database import Database
from api.services import Services
from connectors.article_scraper import ArticleContent, generate_article_id
from connectors.news_connector import SerperNewsConnector
from connectors.youtube_analyzer import YouTubeAnalyzer
from rag.article_store import ArticleStore
from rag.rag_engine import RAGEngine
from user.recommendation_engine import RecommendationEngine
from user.user_profile import UserProfileManager

TESLA = {
    "article_id": "tesla001",
    "url": "https://example.com/tesla",
    "title": "Tesla announces Model Y refresh",
    "content": "Tesla unveiled a refreshed Model Y electric vehicle with longer range and faster charging.",
    "source": "TechNews",
    "category": "Technology",
    "topics": ["Tesla", "EV", "electric vehicle"],
}
BMW = {
    "article_id": "bmw001",
    "url": "https://example.com/bmw",
    "title": "BMW launches the electric iX",
    "content": "BMW launched its iX electric SUV, aiming to compete with Tesla in the luxury EV market.",
    "source": "AutoWorld",
    "category": "Technology",
    "topics": ["BMW", "EV", "electric vehicle"],
}
MARKETS = {
    "article_id": "mkt001",
    "url": "https://example.com/markets",
    "title": "Stock market rallies on earnings",
    "content": "Major indexes rose as bank earnings beat expectations and investors cheered.",
    "source": "FinDaily",
    "category": "Finance",
    "topics": ["stock", "market", "earnings", "bank"],
}


@pytest.fixture
def store() -> ArticleStore:
    s = ArticleStore()
    for article in (MARKETS, BMW, TESLA):
        s.add(dict(article))
    return s


@pytest.fixture
def profiles() -> UserProfileManager:
    return UserProfileManager(score_increment=0.1, decay_factor=0.5)


class RecordingLLM:
    def __init__(self, answer: str = "stub answer"):
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.answer


@pytest.fixture
def llm() -> RecordingLLM:
    return RecordingLLM()


class FakeScraper:
    """Stands in for news-please: turns search results into deterministic articles."""

    def __init__(self):
        self.cleared = False

    async def scrape_articles(self, items, batch_size: int = 5):
        return [
            ArticleContent(
                article_id=generate_article_id(item["url"]),
                url=item["url"],
                title=f"Scraped {item['url'].rsplit('/', 1)[-1]}",
                content="Fresh electric vehicle coverage from the live stream.",
                source=item.get("source", ""),
                category=item.get("category", ""),
                topics=["EV"],
            )
            for item in items
        ]

    def clear_cache(self):
        self.cleared = True

    def get_stats(self):
        return {}

    def shutdown(self):
        pass


@pytest.fixture
def services(tmp_path, store, profiles, llm) -> Services:
    return Services(
        store=store,
        profiles=profiles,
        recommendations=RecommendationEngine(store, profiles),
        rag=RAGEngine(store, generate=llm, pathway_url=""),
        news=SerperNewsConnector(api_key=""),
        scraper=FakeScraper(),
        youtube=YouTubeAnalyzer(serper_key="", openrouter_key=""),
        db=Database(f"sqlite:///{tmp_path / 'test.db'}"),
    )


@pytest.fixture
def client(services):
    from fastapi.testclient import TestClient

    from api.main import create_app

    with TestClient(create_app(services=services, enable_streaming=False)) as test_client:
        yield test_client
