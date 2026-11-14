"""
Pathway live indexing service.

Streams news from Serper, scrapes each article and indexes it incrementally in a Pathway
``DocumentStore``. The store is served over HTTP by Pathway's ``DocumentStoreServer``
(``POST /v1/retrieve``, ``POST /v1/statistics``, ``POST /v1/inputs``), so new articles become
retrievable as soon as they are scraped, without restarts or batch re-indexing.

Run it next to the API and point the API at it::

    python -m pipeline.document_pipeline            # BM25 (no embedding key required)
    python -m pipeline.document_pipeline --retriever hybrid   # BM25 + embeddings (OPENAI_API_KEY)
    PATHWAY_RETRIEVER_URL=http://127.0.0.1:8765 python app.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time
from typing import Any

import pathway as pw
from pathway.stdlib.indexing import BruteForceKnnFactory, HybridIndexFactory, TantivyBM25Factory
from pathway.xpacks.llm.document_store import DocumentStore

from config import Config

logger = logging.getLogger(__name__)

RETRIEVERS = ("bm25", "knn", "hybrid")
METADATA_FIELDS = ("article_id", "url", "title", "source", "category", "publish_date", "topics")


class NewsArticleSchema(pw.Schema):
    article_id: str = pw.column_definition(primary_key=True)
    url: str
    title: str
    content: str
    source: str
    category: str
    publish_date: str | None
    topics: list[str]


def article_to_row(article: dict[str, Any]) -> dict[str, Any]:
    """Project an article dict onto :class:`NewsArticleSchema`."""
    return {
        "article_id": article["article_id"],
        "url": article.get("url") or "",
        "title": article.get("title") or "",
        "content": article.get("content") or "",
        "source": article.get("source") or "",
        "category": article.get("category") or "",
        "publish_date": article.get("publish_date"),
        "topics": list(article.get("topics") or []),
    }


@pw.udf
def _document_bytes(title: str, content: str) -> bytes:
    return f"{title}\n\n{content}".encode()


@pw.udf
def _document_metadata(
    article_id: str, url: str, title: str, source: str, category: str, publish_date: str | None, topics: list[str]
) -> pw.Json:
    return pw.Json(
        {
            "article_id": article_id,
            "url": url,
            "title": title,
            "source": source,
            "category": category,
            "publish_date": publish_date,
            "topics": list(topics),
        }
    )


def articles_to_documents(articles: pw.Table) -> pw.Table:
    """Convert an articles table into the ``data`` / ``_metadata`` layout DocumentStore expects."""
    return articles.select(
        data=_document_bytes(pw.this.title, pw.this.content),
        _metadata=_document_metadata(*(pw.this[name] for name in METADATA_FIELDS)),
    )


def make_retriever_factory(kind: str = "bm25", embedder: pw.UDF | None = None):
    """Build a Pathway retriever factory: ``bm25``, ``knn`` or ``hybrid`` (BM25 + kNN, RRF fused)."""
    if kind not in RETRIEVERS:
        raise ValueError(f"retriever must be one of {RETRIEVERS}")
    if kind == "bm25":
        return TantivyBM25Factory()
    if embedder is None:
        from pathway.xpacks.llm.embedders import OpenAIEmbedder

        embedder = OpenAIEmbedder(model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
    knn = BruteForceKnnFactory(embedder=embedder)
    return knn if kind == "knn" else HybridIndexFactory([TantivyBM25Factory(), knn])


def build_document_store(
    articles: pw.Table,
    retriever: str = "bm25",
    embedder: pw.UDF | None = None,
    chunk: bool = True,
) -> DocumentStore:
    """
    Index ``articles`` in a Pathway DocumentStore.

    With ``chunk=True`` articles are split into ~400-token chunks (needs ``tiktoken``, which
    downloads its encoding on first use); with ``chunk=False`` each article is one document.
    """
    splitter = None
    if chunk:
        from pathway.xpacks.llm.splitters import TokenCountSplitter

        splitter = TokenCountSplitter(min_tokens=50, max_tokens=400)
    return DocumentStore(
        articles_to_documents(articles),
        retriever_factory=make_retriever_factory(retriever, embedder),
        splitter=splitter,
    )


class NewsStreamSubject(pw.io.python.ConnectorSubject):
    """Pathway input connector that polls Serper and pushes scraped articles into the stream."""

    def __init__(self, interval_seconds: int | None = None, max_cycles: int | None = None):
        super().__init__()
        self.interval = interval_seconds or Config.NEWS_FETCH_INTERVAL_SECONDS
        self.max_cycles = max_cycles

    async def _fetch_cycle(self, connector, scraper) -> int:
        results = await connector.fetch_all_categories()
        articles = await scraper.scrape_articles(
            [{"url": r.url, "category": r.category, "source": r.source} for r in results]
        )
        for article in articles:
            self.next(**article_to_row(article.to_dict()))
        return len(articles)

    def run(self) -> None:
        from connectors.article_scraper import ArticleScraper
        from connectors.news_connector import SerperNewsConnector

        connector = SerperNewsConnector()
        scraper = ArticleScraper()
        cycles = 0
        try:
            while self.max_cycles is None or cycles < self.max_cycles:
                indexed = asyncio.run(self._fetch_cycle(connector, scraper))
                logger.info("Pushed %d articles into Pathway", indexed)
                cycles += 1
                if self.max_cycles is None or cycles < self.max_cycles:
                    time.sleep(self.interval)
        finally:
            scraper.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="Pathway live news indexing server")
    parser.add_argument("--host", default=Config.PATHWAY_HOST)
    parser.add_argument("--port", type=int, default=Config.PATHWAY_PORT)
    parser.add_argument("--retriever", choices=RETRIEVERS, default="bm25")
    parser.add_argument("--no-chunking", action="store_true", help="index whole articles instead of chunks")
    args = parser.parse_args()

    logging.basicConfig(level=Config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not Config.SERPER_API_KEY:
        raise SystemExit("SERPER_API_KEY is required to stream news into Pathway")

    from pathway.xpacks.llm.servers import DocumentStoreServer

    articles = pw.io.python.read(NewsStreamSubject(), schema=NewsArticleSchema)
    store = build_document_store(articles, retriever=args.retriever, chunk=not args.no_chunking)
    DocumentStoreServer(host=args.host, port=args.port, document_store=store).run(with_cache=False)


if __name__ == "__main__":
    main()
