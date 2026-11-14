import pytest

from api.services import Services
from connectors.news_connector import NewsSearchResult

ONBOARDING = {
    "user_id": "user_1",
    "categories": ["Finance"],
    "reading_depth": "quick",
    "daily_time": "10_30",
    "content_formats": ["text"],
    "primary_reason": "professional",
    "industry": "Finance",
    "regions": ["International"],
    "ai_summary_preference": "love_it",
    "importance_timely": 5,
    "importance_accurate": 4,
    "importance_engaging": 3,
}


def test_health_and_stats(client):
    assert client.get("/health").json()["status"] == "healthy"
    stats = client.get("/api/stats").json()
    assert stats["rag_engine"]["indexed_documents"] == 3
    assert stats["news_connector"]["configured"] is False


def test_index_page_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "<title>" in response.text


def test_feed_unpersonalised_and_personalised(client):
    plain = client.get("/api/news/feed").json()
    assert plain["personalized"] is False
    assert [a["article_id"] for a in plain["articles"]] == ["tesla001", "bmw001", "mkt001"]
    assert "content" not in plain["articles"][0]

    client.post("/api/onboarding", json=ONBOARDING)
    personal = client.get("/api/news/feed", params={"user_id": "user_1"}).json()
    assert personal["personalized"] is True
    assert personal["articles"][0]["article_id"] == "mkt001"
    assert personal["articles"][0]["source"] == "FinDaily"


def test_feed_rejects_bad_user_id(client):
    assert client.get("/api/news/feed", params={"user_id": "<script>"}).status_code == 422


def test_article_detail_tracks_view(client, services):
    body = client.get("/api/news/article/tesla001", params={"user_id": "u9"}).json()
    assert body["article"]["title"].startswith("Tesla")
    assert body["related_articles"][0]["article_id"] == "bmw001"
    assert body["comparison_suggestion"]["article_ids"] == ["tesla001", "bmw001"]
    assert services.profiles.get_user("u9").viewed_articles == ["tesla001"]
    assert client.get("/api/news/article/nope").status_code == 404


def test_search(client):
    body = client.get("/api/news/search", params={"query": "earnings"}).json()
    assert [r["article_id"] for r in body["results"]] == ["mkt001"]


def test_chat_endpoints(client, llm):
    body = client.post("/api/chat/query", json={"query": "Tesla charging"}).json()
    assert body["response"] == "stub answer"
    assert body["context"]["documents"][0]["article_id"] == "tesla001"

    body = client.post("/api/chat/article/bmw001", json={"query": "Summarise", "user_id": "u1"}).json()
    assert body["context"]["context_type"] == "article"
    assert client.post("/api/chat/article/nope", json={"query": "x"}).status_code == 404

    body = client.post("/api/chat/compare", json={"query": "Compare", "article_ids": ["tesla001", "bmw001"]}).json()
    assert body["context"]["context_type"] == "comparison"
    assert len(llm.calls) == 3


def test_chat_validation(client):
    assert client.post("/api/chat/query", json={"query": ""}).status_code == 422
    assert client.post("/api/chat/compare", json={"query": "x", "article_ids": ["one"]}).status_code == 422
    assert client.post("/api/chat/compare", json={"query": "x", "article_ids": ["a", "b"]}).status_code == 404


def test_interaction_and_preferences(client):
    response = client.post(
        "/api/user/interaction", json={"user_id": "u2", "article_id": "mkt001", "interaction_type": "like"}
    )
    assert response.json()["tracked"] is True
    prefs = client.get("/api/user/u2/preferences").json()
    assert prefs["top_categories"] == ["Finance"]
    assert client.get("/api/user/ghost/preferences").status_code == 404
    bad = client.post("/api/user/interaction", json={"user_id": "u2", "article_id": "mkt001", "interaction_type": "x"})
    assert bad.status_code == 422
    recs = client.get("/api/user/u2/recommendations").json()["recommendations"]
    assert recs[0]["article_id"] == "mkt001"


def test_onboarding_roundtrip_is_idempotent(client):
    assert client.get("/api/onboarding/check/user_1").json() == {"completed": False, "data": None}
    first = client.post("/api/onboarding", json=ONBOARDING).json()
    assert first["message"] == "Onboarding completed successfully"
    second = client.post("/api/onboarding", json={**ONBOARDING, "industry": "Other"}).json()
    assert second["message"] == "Onboarding already completed"
    check = client.get("/api/onboarding/check/user_1").json()
    assert check["completed"] is True
    assert check["data"]["industry"] == "Finance"
    assert check["data"]["completed_at"]


def test_onboarding_validation(client):
    assert client.post("/api/onboarding", json={**ONBOARDING, "importance_timely": 9}).status_code == 422
    assert client.post("/api/onboarding", json={**ONBOARDING, "categories": []}).status_code == 422


def test_fetch_without_serper_key_is_503(client):
    response = client.post("/api/news/fetch", params={"category": "Technology"})
    assert response.status_code == 503
    assert "SERPER_API_KEY" in response.json()["detail"]


def test_fetch_ingests_and_broadcasts(client, services, monkeypatch):
    async def fake_search(category, num_results=None):
        return [
            NewsSearchResult(
                url=f"https://n.com/{category.lower()}-{i}",
                title="t",
                snippet="",
                source="N",
                date=None,
                category=category,
                search_query=category,
                fetched_at="",
            )
            for i in range(2)
        ]

    monkeypatch.setattr(services.news, "search_category", fake_search)
    with client.websocket_connect("/ws/feed") as ws:
        body = client.post("/api/news/fetch", params={"category": "Science", "num_results": 2}).json()
        assert body["count"] == 2
        message = ws.receive_json()
        assert message["type"] == "new_article"
        assert message["article"]["category"] == "Science"
        ws.send_text("ping")
        # The second broadcast is queued before the pong.
        assert ws.receive_json()["type"] == "new_article"
        assert ws.receive_text() == "pong"
    assert len(services.store) == 5


def test_websocket_chat(client):
    with client.websocket_connect("/ws/chat/s1") as ws:
        ws.send_json({"query": "Tesla"})
        reply = ws.receive_json()
        assert reply["session_id"] == "s1"
        assert reply["response"]["response"] == "stub answer"
        ws.send_json({"query": "  "})
        assert ws.receive_json()["error"] == "query is required"


def test_youtube_endpoints(client):
    status = client.get("/api/youtube/status").json()
    assert set(status["dependencies"]) == {"ffmpeg", "whisper", "pytubefix", "yt_dlp"}
    assert client.post("/api/youtube/search", json={"query": "Tesla"}).status_code == 503
    bad = client.post("/api/youtube/analyze", json={"video_url": "https://evil.com/x", "article_title": "t"})
    assert bad.status_code == 422


def test_admin_requires_token(client, monkeypatch):
    from config import Config

    monkeypatch.setattr(Config, "ADMIN_TOKEN", None)
    assert client.post("/api/admin/clear-cache").status_code == 403
    monkeypatch.setattr(Config, "ADMIN_TOKEN", "secret")
    assert client.post("/api/admin/clear-cache", headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert client.post("/api/admin/clear-cache", headers={"X-Admin-Token": "secret"}).status_code == 200


@pytest.mark.parametrize("path", ["/docs", "/openapi.json"])
def test_docs_available(client, path):
    assert client.get(path).status_code == 200


def test_services_create_uses_given_database(tmp_path):
    services = Services.create(database_url=f"sqlite:///{tmp_path / 'x' / 'db.sqlite'}")
    services.db.create_tables()
    assert (tmp_path / "x" / "db.sqlite").exists()
    services.shutdown()


def test_unknown_page_returns_html_404_for_browsers(client):
    response = client.get("/no-such-page", headers={"Accept": "text/html"})
    assert response.status_code == 404
    assert "Page not found" in response.text


def test_unknown_api_route_keeps_json_404(client):
    response = client.get("/api/no-such-route", headers={"Accept": "text/html"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert client.get("/no-such-page").json() == {"detail": "Not Found"}


def test_demo_mode_preloads_sample_articles(tmp_path):
    from fastapi.testclient import TestClient

    from api.demo_data import DEMO_SOURCE
    from api.main import create_app

    services = Services.create(database_url=f"sqlite:///{tmp_path / 'demo.db'}")
    with TestClient(create_app(services=services, enable_streaming=False, demo=True)) as demo_client:
        articles = demo_client.get("/api/news/feed?limit=50").json()["articles"]
        assert len(articles) >= 6
        assert {a["source"] for a in articles} == {DEMO_SOURCE}
        assert all(a["url"].startswith("https://example.com/") for a in articles)
        assert all(a["topics"] for a in articles)
