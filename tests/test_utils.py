from datetime import timezone

from utils import parse_datetime, parse_topics, tokenize


def test_parse_topics_accepts_lists_json_and_garbage():
    assert parse_topics(["a", "", "b"]) == ["a", "b"]
    assert parse_topics('["x", "y"]') == ["x", "y"]
    assert parse_topics("plain") == ["plain"]
    assert parse_topics(None) == []
    assert parse_topics(42) == []


def test_tokenize_strips_punctuation_and_stopwords():
    assert tokenize("What's happening with Tesla?") == ["s", "tesla"]
    assert tokenize("The EV market", drop_stopwords=False) == ["the", "ev", "market"]


def test_parse_datetime_normalises_to_utc():
    parsed = parse_datetime("2026-01-01T10:00:00+05:30")
    assert parsed.tzinfo == timezone.utc
    assert parsed.hour == 4 and parsed.minute == 30
    assert parse_datetime("2026-01-01T10:00:00").tzinfo == timezone.utc
    assert parse_datetime("2026-01-01T10:00:00Z").hour == 10
    assert parse_datetime("not a date") is None
    assert parse_datetime(None) is None
