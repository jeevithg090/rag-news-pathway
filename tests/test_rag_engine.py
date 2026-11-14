import httpx
import pytest

from rag.rag_engine import LLM_NOT_CONFIGURED_MESSAGE, NO_CONTEXT_MESSAGE, RAGEngine


async def test_global_query_grounds_prompt_in_retrieved_articles(store, llm):
    engine = RAGEngine(store, generate=llm, pathway_url="")
    response = await engine.query_global("Tesla range")

    assert response.response == "stub answer"
    assert response.context.retriever == "keyword"
    assert response.context.documents[0]["article_id"] == "tesla001"
    _, prompt = llm.calls[0]
    assert "Tesla announces Model Y refresh" in prompt
    assert "Tesla range" in prompt


async def test_global_query_without_matches_skips_llm(store, llm):
    engine = RAGEngine(store, generate=llm, pathway_url="")
    response = await engine.query_global("cricket world cup")
    assert response.response == NO_CONTEXT_MESSAGE
    assert llm.calls == []


async def test_missing_api_key_returns_helpful_message(store):
    engine = RAGEngine(store, api_key="", pathway_url="")
    assert not engine.llm_configured
    response = await engine.query_global("Tesla")
    assert response.response == LLM_NOT_CONFIGURED_MESSAGE
    assert response.context.documents  # still shows what was retrieved


async def test_article_query_expands_with_related_but_not_itself(store, llm):
    engine = RAGEngine(store, generate=llm, pathway_url="")
    response = await engine.query_article("What changed?", "tesla001", top_k=1)
    ids = [d["article_id"] for d in response.context.documents]
    assert ids[0] == "tesla001"
    assert len(ids) == 2 and ids.count("tesla001") == 1


async def test_article_query_without_expansion(store, llm):
    engine = RAGEngine(store, generate=llm, pathway_url="")
    response = await engine.query_article("What changed?", "tesla001", expand_context=False)
    assert [d["article_id"] for d in response.context.documents] == ["tesla001"]
    assert "No related articles available." in llm.calls[0][1]


async def test_article_query_unknown_id(store, llm):
    engine = RAGEngine(store, generate=llm, pathway_url="")
    response = await engine.query_article("?", "nope")
    assert "not found" in response.response
    assert llm.calls == []


async def test_comparison_mentions_missing_ids(store, llm):
    engine = RAGEngine(store, generate=llm, pathway_url="")
    response = await engine.query_comparison("Compare", ["tesla001", "bmw001", "ghost"])
    assert [d["article_id"] for d in response.context.documents] == ["tesla001", "bmw001"]
    assert "ghost" in llm.calls[0][1]


def test_to_dict_includes_snippets(store):
    import asyncio

    async def answer(*_):
        return "ok"

    engine = RAGEngine(store, generate=answer, pathway_url="")
    payload = asyncio.run(engine.query_global("Tesla")).to_dict()
    doc = payload["context"]["documents"][0]
    assert doc["snippet"].startswith("Tesla unveiled")
    assert doc["url"] == "https://example.com/tesla"


class _FakePathwayTransport(httpx.AsyncBaseTransport):
    def __init__(self, hits):
        self.hits = hits
        self.requests = []

    async def handle_async_request(self, request):
        self.requests.append(request)
        return httpx.Response(200, json=self.hits)


@pytest.fixture
def patch_httpx(monkeypatch):
    def install(transport):
        original = httpx.AsyncClient

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", factory)

    return install


async def test_pathway_retriever_used_when_configured(store, llm, patch_httpx):
    transport = _FakePathwayTransport(
        [
            {"text": "chunk 1", "metadata": {"article_id": "bmw001"}, "dist": 0.1},
            {"text": "chunk 2", "metadata": {"article_id": "bmw001"}, "dist": 0.2},
            {"text": "remote only", "metadata": {"article_id": "remote1", "title": "Remote"}, "dist": 0.3},
        ]
    )
    patch_httpx(transport)
    engine = RAGEngine(store, generate=llm, pathway_url="http://pathway:8765/")
    response = await engine.query_global("electric", category="Technology")

    assert response.context.retriever == "pathway"
    assert [d["article_id"] for d in response.context.documents] == ["bmw001", "remote1"]
    assert response.context.documents[0]["title"] == "BMW launches the electric iX"  # full local copy
    assert response.context.documents[1]["content"] == "remote only"
    assert str(transport.requests[0].url) == "http://pathway:8765/v1/retrieve"
    assert b"category == `Technology`" in transport.requests[0].content


async def test_pathway_failure_falls_back_to_keyword(store, llm, patch_httpx):
    class Failing(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ConnectError("down")

    patch_httpx(Failing())
    engine = RAGEngine(store, generate=llm, pathway_url="http://pathway:8765")
    response = await engine.query_global("Tesla")
    assert response.context.retriever == "keyword"
    assert response.context.documents[0]["article_id"] == "tesla001"
