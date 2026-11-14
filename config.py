"""Application configuration, read from environment variables (and an optional `.env`)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent


def _env_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    value = _env_str(name)
    return int(value) if value is not None else default


def _env_float(name: str, default: float) -> float:
    value = _env_str(name)
    return float(value) if value is not None else default


def _env_bool(name: str, default: bool) -> bool:
    value = _env_str(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    value = _env_str(name)
    if value is None:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


class Config:
    """Central configuration. Values are resolved once at import time."""

    # --- External APIs -----------------------------------------------------
    SERPER_API_KEY = _env_str("SERPER_API_KEY")
    SERPER_NEWS_URL = "https://google.serper.dev/news"
    SERPER_VIDEOS_URL = "https://google.serper.dev/videos"

    OPENROUTER_API_KEY = _env_str("OPENROUTER_API_KEY")
    LLM_BASE_URL = _env_str("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    LLM_MODEL = _env_str("LLM_MODEL", "openai/gpt-4o")
    LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0.7)
    LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 2000)
    LLM_TIMEOUT_SECONDS = _env_float("LLM_TIMEOUT_SECONDS", 60.0)

    # --- HTTP server ---------------------------------------------------------
    HOST = _env_str("HOST", "127.0.0.1")
    PORT = _env_int("PORT", 8000)
    LOG_LEVEL = _env_str("LOG_LEVEL", "INFO")
    # Comma-separated list of allowed browser origins for CORS.
    CORS_ORIGINS = _env_list("CORS_ORIGINS", ["http://localhost:3000", "http://127.0.0.1:3000"])
    # Token required by admin endpoints. Admin endpoints are disabled when unset.
    ADMIN_TOKEN = _env_str("ADMIN_TOKEN")

    # --- Persistence ---------------------------------------------------------
    DATABASE_URL = _env_str("DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'data' / 'news_ai.db'}")

    # --- News ingestion ------------------------------------------------------
    NEWS_CATEGORIES = _env_list(
        "NEWS_CATEGORIES",
        [
            "Finance",
            "Technology",
            "Science",
            "Business",
            "Health",
            "Entertainment",
            "Sports",
            "Politics",
            "World",
        ],
    )
    NEWS_FETCH_INTERVAL_SECONDS = _env_int("NEWS_FETCH_INTERVAL_SECONDS", 300)
    NEWS_RESULTS_PER_CATEGORY = _env_int("NEWS_RESULTS_PER_CATEGORY", 10)
    # Start the background Serper -> scraper -> index loop with the API server.
    NEWS_STREAMING_ENABLED = _env_bool("NEWS_STREAMING_ENABLED", False)
    # Pre-load fictional sample articles at startup (for trying the UI without API keys).
    DEMO_MODE = _env_bool("DEMO_MODE", False)

    # --- Retrieval / RAG -----------------------------------------------------
    RAG_TOP_K = _env_int("RAG_TOP_K", 5)
    RAG_CONTEXT_CHARS = _env_int("RAG_CONTEXT_CHARS", 2000)
    # Base URL of a running Pathway DocumentStore server (see pipeline/). When set,
    # global chat queries retrieve from it; otherwise the in-process keyword index is used.
    PATHWAY_RETRIEVER_URL = _env_str("PATHWAY_RETRIEVER_URL")
    PATHWAY_HOST = _env_str("PATHWAY_HOST", "127.0.0.1")
    PATHWAY_PORT = _env_int("PATHWAY_PORT", 8765)

    # --- Personalisation -----------------------------------------------------
    PREFERENCE_SCORE_INCREMENT = _env_float("PREFERENCE_SCORE_INCREMENT", 0.1)
    PREFERENCE_DECAY_FACTOR = _env_float("PREFERENCE_DECAY_FACTOR", 0.95)

    # --- YouTube analysis (optional extra) -----------------------------------
    WHISPER_MODEL = _env_str("WHISPER_MODEL", "base")
    CACHE_DIR = Path(_env_str("CACHE_DIR", str(PROJECT_ROOT / "cache")))
