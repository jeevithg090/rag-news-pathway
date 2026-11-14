"""
RAG engine with three context modes:

* **global** - retrieve across every indexed article (optionally from a Pathway DocumentStore),
* **article** - focus on one article and expand context with topically related articles,
* **comparison** - merge several chosen articles into one comparative prompt.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from config import Config
from rag.article_store import ArticleStore
from utils import utcnow_iso

logger = logging.getLogger(__name__)

GenerateFn = Callable[[str, str], Awaitable[str]]

NO_CONTEXT_MESSAGE = (
    "I don't have any relevant news articles to answer this question yet. "
    "Try a different query, or fetch more news first."
)
LLM_NOT_CONFIGURED_MESSAGE = (
    "The language model is not configured. Set OPENROUTER_API_KEY to enable AI answers; "
    "the retrieved articles are listed below."
)
LLM_ERROR_MESSAGE = "Sorry, the language model request failed. Please try again in a moment."

GLOBAL_SYSTEM_PROMPT = """You are a knowledgeable AI news analyst. Answer questions about current \
news using the provided article context.

Guidelines:
- Base your answers primarily on the provided articles
- If the articles don't contain enough information, say so
- Mention specific sources when citing information
- Be concise but informative and highlight key developments"""

ARTICLE_SYSTEM_PROMPT = """You are an AI assistant helping users understand news articles. Focus \
primarily on the main article but reference related articles when relevant.

Guidelines:
- Answer based on the main article first
- Use related articles to provide additional context
- If the user asks about something not in the articles, say so
- Be conversational and helpful"""

COMPARISON_SYSTEM_PROMPT = """You are an AI analyst specialising in comparative news analysis. \
Compare and contrast information from multiple news articles.

Guidelines:
- Identify key similarities and differences
- Highlight important points from each article
- Provide balanced analysis with specific details
- Structure your comparison clearly"""


@dataclass
class RAGContext:
    """Documents retrieved for a query."""

    documents: list[dict[str, Any]]
    query: str
    context_type: str  # "global", "article" or "comparison"
    metadata_filter: str | None = None
    retriever: str = "keyword"


@dataclass
class RAGResponse:
    """Answer plus the context it was grounded on."""

    query: str
    response: str
    context: RAGContext
    model: str
    created_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "response": self.response,
            "model": self.model,
            "created_at": self.created_at,
            "context": {
                "query": self.context.query,
                "context_type": self.context.context_type,
                "metadata_filter": self.context.metadata_filter,
                "retriever": self.context.retriever,
                "documents": [
                    {
                        "article_id": doc.get("article_id"),
                        "title": doc.get("title"),
                        "source": doc.get("source"),
                        "url": doc.get("url"),
                        "snippet": (doc.get("content") or doc.get("text") or "")[:200],
                    }
                    for doc in self.context.documents
                ],
            },
        }


def build_context_text(documents: list[dict[str, Any]], max_chars: int | None = None) -> str:
    """Render documents as numbered, delimited blocks for the prompt."""
    max_chars = max_chars or Config.RAG_CONTEXT_CHARS
    parts = []
    for i, doc in enumerate(documents, 1):
        parts.append(
            f"Article {i}: {doc.get('title') or 'Untitled'}\n"
            f"Source: {doc.get('source') or 'Unknown'} | Category: {doc.get('category') or ''}\n"
            f"Published: {doc.get('publish_date') or 'Unknown date'}\n"
            f"---\n{(doc.get('content') or '')[:max_chars]}\n---"
        )
    return "\n\n".join(parts)


class PathwayRetriever:
    """Client for a Pathway ``DocumentStoreServer`` (``POST /v1/retrieve``)."""

    def __init__(self, base_url: str, store: ArticleStore, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.store = store
        self.timeout = timeout

    async def retrieve(self, query: str, k: int, category: str | None = None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"query": query, "k": k}
        if category:
            # JMESPath filter evaluated by Pathway against document metadata.
            payload["metadata_filter"] = f"category == `{category}`"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/v1/retrieve", json=payload)
            response.raise_for_status()
            hits = response.json()

        documents: list[dict[str, Any]] = []
        seen: set[str] = set()
        for hit in hits:
            metadata = hit.get("metadata") or {}
            article_id = metadata.get("article_id")
            if article_id in seen:
                continue
            if article_id:
                seen.add(article_id)
            # Prefer the full article if we have it locally; otherwise use the chunk.
            local = self.store.get(article_id) if article_id else None
            documents.append(local or {**metadata, "content": hit.get("text", "")})
        return documents


class RAGEngine:
    """Retrieval-augmented question answering over the shared article store."""

    def __init__(
        self,
        store: ArticleStore,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        generate: GenerateFn | None = None,
        pathway_url: str | None = None,
    ):
        self.store = store
        self.api_key = api_key if api_key is not None else Config.OPENROUTER_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL
        self._generate_override = generate
        self._client = None
        pathway_url = pathway_url if pathway_url is not None else Config.PATHWAY_RETRIEVER_URL
        self.pathway = PathwayRetriever(pathway_url, store) if pathway_url else None

    # ------------------------------------------------------------------ LLM
    @property
    def llm_configured(self) -> bool:
        return self._generate_override is not None or bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, timeout=Config.LLM_TIMEOUT_SECONDS)
        return self._client

    async def _generate(self, system_prompt: str, user_prompt: str) -> str:
        if self._generate_override is not None:
            return await self._generate_override(system_prompt, user_prompt)
        if not self.api_key:
            return LLM_NOT_CONFIGURED_MESSAGE
        try:
            completion = await self._get_client().chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=Config.LLM_TEMPERATURE,
                max_tokens=Config.LLM_MAX_TOKENS,
            )
            return completion.choices[0].message.content or ""
        except Exception:
            logger.exception("LLM request failed")
            return LLM_ERROR_MESSAGE

    def _response(self, query: str, answer: str, context: RAGContext) -> RAGResponse:
        return RAGResponse(query=query, response=answer, context=context, model=self.model)

    # ------------------------------------------------------------ retrieval
    async def retrieve(self, query: str, top_k: int, category: str | None = None) -> tuple[list[dict], str]:
        """Retrieve from Pathway when configured (falling back to keywords on error)."""
        if self.pathway is not None:
            try:
                return await self.pathway.retrieve(query, top_k, category), "pathway"
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("Pathway retrieval failed, using keyword search: %s", exc)
        return self.store.search(query, top_k=top_k, category=category), "keyword"

    # -------------------------------------------------------------- queries
    async def query_global(self, query: str, top_k: int | None = None, category: str | None = None) -> RAGResponse:
        top_k = top_k or Config.RAG_TOP_K
        documents, retriever = await self.retrieve(query, top_k, category)
        context = RAGContext(
            documents=documents,
            query=query,
            context_type="global",
            metadata_filter=f"category={category}" if category else None,
            retriever=retriever,
        )
        if not documents:
            return self._response(query, NO_CONTEXT_MESSAGE, context)

        user_prompt = (
            "Based on the following news articles, answer this question.\n\n"
            f"**Question:** {query}\n\n"
            f"**Context (retrieved articles):**\n{build_context_text(documents)}"
        )
        return self._response(query, await self._generate(GLOBAL_SYSTEM_PROMPT, user_prompt), context)

    async def query_article(
        self, query: str, article_id: str, expand_context: bool = True, top_k: int = 3
    ) -> RAGResponse:
        main_article = self.store.get(article_id)
        if not main_article:
            context = RAGContext(documents=[], query=query, context_type="article")
            return self._response(query, f"Article with ID '{article_id}' not found.", context)

        documents = [main_article]
        topics = main_article.get("topics", [])
        if expand_context and topics:
            related = self.store.search(" ".join(topics[:3]), top_k=top_k + 1)
            documents.extend(doc for doc in related if doc["article_id"] != article_id)
            documents = documents[: top_k + 1]

        context = RAGContext(
            documents=documents,
            query=query,
            context_type="article",
            metadata_filter=f"article_id={article_id}",
        )
        related_text = build_context_text(documents[1:]) if len(documents) > 1 else "No related articles available."
        user_prompt = (
            "The user is reading the following news article and has a question.\n\n"
            f"**MAIN ARTICLE:**\n{build_context_text([main_article])}\n\n"
            f"**RELATED ARTICLES (for context):**\n{related_text}\n\n"
            f"**User's question:** {query}"
        )
        return self._response(query, await self._generate(ARTICLE_SYSTEM_PROMPT, user_prompt), context)

    async def query_comparison(self, query: str, article_ids: list[str]) -> RAGResponse:
        documents = self.store.get_many(article_ids)
        found = {doc["article_id"] for doc in documents}
        missing = [aid for aid in article_ids if aid not in found]

        context = RAGContext(
            documents=documents,
            query=query,
            context_type="comparison",
            metadata_filter=f"article_ids={','.join(article_ids)}",
        )
        if not documents:
            return self._response(query, "None of the specified articles were found.", context)

        user_prompt = (
            "Analyse and compare the following articles.\n\n"
            f"{build_context_text(documents, max_chars=2500)}\n\n"
            f"**Comparison request:** {query}"
        )
        if missing:
            user_prompt += f"\n\nNote: these article IDs were not found: {', '.join(missing)}"
        return self._response(query, await self._generate(COMPARISON_SYSTEM_PROMPT, user_prompt), context)

    def get_stats(self) -> dict[str, Any]:
        return {
            "indexed_documents": len(self.store),
            "model": self.model,
            "llm_configured": self.llm_configured,
            "retriever": "pathway" if self.pathway else "keyword",
        }
