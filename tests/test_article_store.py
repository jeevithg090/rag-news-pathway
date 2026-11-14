from rag.article_store import ArticleStore


def test_add_reports_new_and_normalises_topics():
    store = ArticleStore()
    assert store.add({"article_id": "a", "title": "T", "topics": '["x"]'}) is True
    assert store.add({"article_id": "a", "title": "T2"}) is False
    assert store.add({"title": "no id"}) is False
    assert len(store) == 1
    assert store.get("a")["title"] == "T2"
    assert store.get("a")["topics"] == []


def test_all_is_newest_first(store):
    assert [a["article_id"] for a in store.all()] == ["tesla001", "bmw001", "mkt001"]


def test_search_ranks_topic_and_title_matches(store):
    results = store.search("Tesla electric?", top_k=5)
    assert results[0]["article_id"] == "tesla001"
    assert {r["article_id"] for r in results} == {"tesla001", "bmw001"}


def test_search_filters_by_category_and_ids(store):
    assert [r["article_id"] for r in store.search("electric", category="finance")] == []
    assert [r["article_id"] for r in store.search("earnings", category="FINANCE")] == ["mkt001"]
    assert [r["article_id"] for r in store.search("electric", article_ids=["bmw001"])] == ["bmw001"]


def test_search_ignores_stopword_only_queries(store):
    assert store.search("what is the") == []


def test_search_respects_top_k(store):
    assert len(store.search("electric vehicle market", top_k=1)) == 1


def test_search_matches_category_name(store):
    # "finance" appears in no title, topic or body, only as the category of the markets article.
    results = store.search("latest finance news")
    assert [doc["article_id"] for doc in results] == ["mkt001"]
