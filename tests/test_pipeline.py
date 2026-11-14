"""Exercises the real Pathway DocumentStore on a static table (BM25, no network)."""

import pytest

pw = pytest.importorskip("pathway")

from pathway.xpacks.llm.document_store import DocumentStore  # noqa: E402

from pipeline.document_pipeline import (  # noqa: E402
    NewsArticleSchema,
    article_to_row,
    build_document_store,
    make_retriever_factory,
)
from tests.conftest import BMW, MARKETS, TESLA  # noqa: E402


def _retrieve(query: str, k: int = 3, metadata_filter: str | None = None):
    rows = [article_to_row(a) for a in (TESLA, BMW, MARKETS)]
    articles = pw.debug.table_from_rows(
        NewsArticleSchema, [tuple(row[c] for c in NewsArticleSchema.column_names()) for row in rows]
    )
    store = build_document_store(articles, chunk=False)
    queries = pw.debug.table_from_rows(DocumentStore.RetrieveQuerySchema, [(query, k, metadata_filter, None)])
    result = pw.debug.table_to_pandas(store.retrieve_query(queries))
    return [hit["metadata"] for hit in result.iloc[0]["result"].value]


def test_bm25_retrieval_returns_relevant_article_with_metadata():
    hits = _retrieve("earnings bank", k=1)
    assert hits[0]["article_id"] == "mkt001"
    assert hits[0]["topics"] == ["stock", "market", "earnings", "bank"]


def test_metadata_filter_by_category():
    hits = _retrieve("electric", k=3, metadata_filter="category == `Technology`")
    assert {h["article_id"] for h in hits} == {"tesla001", "bmw001"}


def test_article_to_row_defaults():
    row = article_to_row({"article_id": "x"})
    assert row == {
        "article_id": "x",
        "url": "",
        "title": "",
        "content": "",
        "source": "",
        "category": "",
        "publish_date": None,
        "topics": [],
    }


def test_unknown_retriever_rejected():
    with pytest.raises(ValueError):
        make_retriever_factory("magic")
