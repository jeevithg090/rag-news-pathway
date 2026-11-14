"""Small helpers shared across modules."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Very common words that carry no retrieval signal.
STOPWORDS = frozenset(
    """
    a an and are as at be but by can could did do does for from had has have how i if in
    into is it its me my of on or our so than that the their them then there these they
    this to was we were what when where which who whom why will with would you your
    about any all latest new news happening
    """.split()
)


def utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def parse_topics(value: Any) -> list[str]:
    """Normalise an article's ``topics`` field (list or JSON-encoded list) to a list of strings."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item]
    return []


def tokenize(text: str, drop_stopwords: bool = True) -> list[str]:
    """Lower-case alphanumeric tokens, optionally without stopwords."""
    tokens = _TOKEN_RE.findall(text.lower())
    if drop_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS]
    return tokens


def parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string into an aware UTC datetime (naive values are assumed UTC)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
