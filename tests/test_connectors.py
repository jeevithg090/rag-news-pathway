import httpx
import pytest

from connectors.article_scraper import extract_topics, generate_article_id
from connectors.news_connector import MissingAPIKeyError, SerperNewsConnector
from connectors.youtube_analyzer import detect_sentiment, extract_key_points, extract_video_id


def test_article_id_is_stable_and_short():
    assert generate_article_id("https://a.com/x") == generate_article_id("https://a.com/x")
    assert generate_article_id("https://a.com/x") != generate_article_id("https://a.com/y")
    assert len(generate_article_id("https://a.com/x")) == 16


def test_extract_topics_matches_whole_words_only():
    topics = extract_topics("Tesla stock jumps", "The EV maker beat earnings. Scary appliances.")
    assert topics == ["stock", "earnings", "Tesla", "EV"]
    # "AI" must not match inside "said" / "maintain"
    assert "AI" not in extract_topics("He said", "maintain")


async def test_serper_connector_parses_and_dedupes():
    payload = {
        "news": [
            {"link": "https://n.com/1", "title": "One", "source": "N"},
            {"link": "https://n.com/1", "title": "Dup"},
            {"link": "", "title": "No link"},
            {"link": "https://n.com/2", "title": "Two"},
        ]
    }
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    connector = SerperNewsConnector(api_key="k", transport=httpx.MockTransport(handler))
    results = await connector.search_category("Technology", num_results=4)
    assert [r.url for r in results] == ["https://n.com/1", "https://n.com/2"]
    assert all(r.category == "Technology" for r in results)
    assert seen[0].headers["X-API-KEY"] == "k"
    # Second call returns nothing new.
    assert await connector.search_category("Technology") == []


async def test_serper_connector_http_error_returns_empty():
    connector = SerperNewsConnector(api_key="k", transport=httpx.MockTransport(lambda r: httpx.Response(500, json={})))
    assert await connector.search_news("x") == []


async def test_serper_connector_requires_key():
    with pytest.raises(MissingAPIKeyError):
        await SerperNewsConnector(api_key="").search_news("x")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?si=x", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://evil.com/watch?v=dQw4w9WgXcQ", None),
        ("file:///etc/passwd", None),
        ("https://www.youtube.com/watch?v=short", None),
        ("not a url", None),
    ],
)
def test_extract_video_id(url, expected):
    assert extract_video_id(url) == expected


def test_key_points_and_sentiment():
    analysis = "**Key points**\n- First point\n2. Second point\n* **Third**\nplain line\n**Sentiment**: Negative"
    assert extract_key_points(analysis) == ["First point", "Second point", "Third"]
    assert detect_sentiment(analysis) == "negative"
    assert detect_sentiment("Overall an optimistic take") == "positive"
    assert detect_sentiment("Nothing notable") == "neutral"
