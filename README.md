# Live AI News

A real-time, personalised news platform. It continuously discovers fresh articles, indexes them
as they arrive and lets readers chat with an LLM about the news, compare articles side by side
and get a feed ranked by what they actually read. New articles become searchable without a
restart or a batch re-index.

Built for the DataQuest 2026 "Live AI" hackathon (IIT Kharagpur), whose brief was a dynamic RAG
application on the [Pathway](https://github.com/pathwaycom/pathway) framework. See
[`docs/hackathon-brief.md`](docs/hackathon-brief.md).

## Features

- **Live ingestion**: polls the [Serper](https://serper.dev) Google News API per category,
  scrapes full article text with [news-please](https://github.com/fhamborg/news-please) and
  tags topics. You can run it on demand (*Fetch News*) or as a background stream.
- **Retrieval-augmented chat** in three modes:
  - *global*: ask about everything indexed, optionally filtered by category
  - *article*: ask about one article, with context widened to related articles
  - *comparison*: compare two to five chosen articles
- **Pathway live index** (optional): a Pathway `DocumentStore` (BM25, kNN or hybrid) fed by a
  streaming connector and served over HTTP. When it is configured, the API retrieves from it.
- **Personalisation**: views, chats, likes and comparisons update each reader's category and
  topic scores. The feed is ranked by those scores, plus freshness and novelty, and each
  ranking comes with the reasons behind it.
- **Smart comparisons**: reading about one side of a rivalry (e.g. Tesla) brings up an article
  about the other (e.g. BMW).
- **Onboarding questionnaire**: a React app that asks nine short questions. The categories a
  reader picks seed their profile.
- **Live updates**: newly indexed articles are pushed to browsers over a WebSocket.
- **YouTube analysis** (optional): finds related videos, then transcribes one with Whisper and
  summarises its stance compared with the article.

## Tech stack

| Layer | Technology |
|-------|------------|
| API | Python 3.10+, FastAPI, Uvicorn, Pydantic v2 |
| Streaming index | Pathway (`DocumentStore`, Tantivy BM25, brute-force kNN, `DocumentStoreServer`) |
| LLM | Any OpenAI-compatible endpoint (OpenRouter by default, `openai/gpt-4o`) |
| Ingestion | Serper API, news-please, httpx |
| Persistence | SQLAlchemy 2 (SQLite by default; any SQLAlchemy URL works) |
| Frontend | Vanilla HTML/CSS/JS main app; React 19 + Vite onboarding app |
| Tooling | pytest, Ruff (lint + format), ESLint |

## Architecture

```
                    ┌────────────────────┐
  Serper News API ─▶│ SerperNewsConnector│── new URLs ──┐
                    └────────────────────┘              ▼
                                               ┌─────────────────┐
                                               │ ArticleScraper  │ news-please, topic tagging
                                               └────────┬────────┘
                       ┌────────────────────────────────┼─────────────────────────────┐
                       ▼                                ▼                             │
        ┌──────────────────────────┐      ┌───────────────────────────┐               │
        │ ArticleStore (in-process)│      │ Pathway DocumentStore     │  optional,    │
        │ feed · keyword retrieval │      │ BM25 / kNN / hybrid index │  separate     │
        └────────────┬─────────────┘      │ DocumentStoreServer :8765 │  process      │
                     │                    └─────────────┬─────────────┘               │
                     ▼                                  │ POST /v1/retrieve           │
  ┌───────────────────────────────────────────────────────────────────┐               │
  │ FastAPI (api/main.py)                                              │◀── /ws/feed ──┘
  │  RAGEngine ── global / article / comparison prompts ──▶ LLM        │   new_article
  │  RecommendationEngine ◀── UserProfileManager (interaction scores)  │   broadcasts
  │  Onboarding (SQLAlchemy)                                           │
  └───────────────────────────────┬───────────────────────────────────┘
                                  │ REST + WebSocket
                ┌─────────────────┴──────────────────┐
                │ Web UI (/)    Onboarding (/onboarding/) │
                └────────────────────────────────────┘
```

- The API keeps articles and user profiles **in memory**. They reset on restart. Onboarding
  answers are persisted in the database and re-seed a profile when that reader comes back.
- Without `PATHWAY_RETRIEVER_URL`, global chat uses the in-process keyword retriever. With it,
  global chat queries Pathway and falls back to keywords if Pathway is unreachable. Article
  and comparison chat always use the in-process store, because they work from article IDs.
- The Pathway service runs its own Serper → scraper loop, so its index fills independently of
  the API's in-memory feed.

## Getting started

### Prerequisites

- Python 3.10–3.13
- Node.js 20+ (only to build or develop the onboarding app)
- A [Serper](https://serper.dev) API key for live news, and an [OpenRouter](https://openrouter.ai)
  (or other OpenAI-compatible) key for AI answers. The app starts without them. Endpoints that
  need a missing key return `503`, and chat returns the retrieved articles without an AI answer.

### Install

```bash
git clone https://github.com/jeevithg090/rag-news-pathway.git
cd rag-news-pathway

python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt        # runtime + pytest + ruff

cp .env.example .env                       # then fill in your keys

npm --prefix frontend/onboarding-app ci    # optional: onboarding app
npm run build                              # builds it into frontend/onboarding-app/dist
```

### Run

```bash
python app.py                  # http://127.0.0.1:8000 (UI), /docs (OpenAPI)
python app.py --stream         # also poll Serper and index news in the background
npm run server                 # same API with auto-reload (uvicorn api.main:app --reload)
npm run dev                    # API + onboarding dev server on :3000 (needs root `npm install`)
```

Live Pathway index (optional, in a second terminal):

```bash
python -m pipeline.document_pipeline                     # BM25, no embedding key needed
python -m pipeline.document_pipeline --retriever hybrid  # BM25 + embeddings (OPENAI_API_KEY)
PATHWAY_RETRIEVER_URL=http://127.0.0.1:8765 python app.py
```

`TokenCountSplitter` chunking uses `tiktoken`, which downloads its encoding on first run. Pass
`--no-chunking` to index whole articles when the machine is offline.

YouTube analysis (optional): install `ffmpeg`, then `pip install -r requirements-youtube.txt`.
`GET /api/youtube/status` reports what is missing.

### Test, lint, build

```bash
python -m pytest               # 69 tests: store, RAG, personalisation, connectors, Pathway, API
ruff check . && ruff format --check .
npm --prefix frontend/onboarding-app run lint
npm run build
```

The tests stub out Serper, the scraper and the LLM, so they need no keys or network. The
Pathway tests build a real BM25 `DocumentStore` on static tables.

## Configuration

All settings are environment variables. They are also read from `.env`; see
[`.env.example`](.env.example).

| Variable | Default | Purpose |
|----------|---------|---------|
| `SERPER_API_KEY` | – | Serper key for news and video search (required for ingestion) |
| `OPENROUTER_API_KEY` | – | LLM key (required for AI answers) |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible endpoint |
| `LLM_MODEL` | `openai/gpt-4o` | Model name at that endpoint |
| `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | `0.7` / `2000` | Generation settings |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Bind address. Use `0.0.0.0` in containers |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Browser origins allowed to call the API |
| `ADMIN_TOKEN` | – | Enables `POST /api/admin/clear-cache` (send it as `X-Admin-Token`) |
| `DATABASE_URL` | `sqlite:///./data/news_ai.db` | SQLAlchemy URL for onboarding data |
| `NEWS_STREAMING_ENABLED` | `false` | Start background ingestion with the API (or `--stream`) |
| `NEWS_FETCH_INTERVAL_SECONDS` | `300` | Delay between polling cycles |
| `NEWS_CATEGORIES` | Finance, Technology, … | Comma-separated categories to poll |
| `RAG_TOP_K` | `5` | Articles retrieved for global chat |
| `PATHWAY_RETRIEVER_URL` | – | Pathway server used for global retrieval |
| `PATHWAY_HOST` / `PATHWAY_PORT` | `127.0.0.1` / `8765` | Bind address of the Pathway server |
| `OPENAI_API_KEY`, `EMBEDDING_MODEL` | –, `text-embedding-3-small` | Only for `--retriever knn` or `hybrid` |
| `WHISPER_MODEL` | `base` | Whisper model size for video transcription |
| `LOG_LEVEL` | `INFO` | Python log level |

## API overview

Interactive docs are at `/docs`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health`, `/api/stats` | Liveness and component statistics |
| GET | `/api/news/feed?user_id=&limit=` | Latest articles, ranked for `user_id` when given |
| GET | `/api/news/article/{id}?user_id=` | Article, related articles, comparison suggestion (records a view) |
| GET | `/api/news/search?query=&category=` | Keyword search over indexed articles |
| POST | `/api/news/fetch?category=&num_results=` | Fetch, scrape and index now |
| POST | `/api/chat/query` | Global RAG question `{query, category?}` |
| POST | `/api/chat/article/{id}` | Article-focused question `{query, expand_context?}` |
| POST | `/api/chat/compare` | Compare `{article_ids: [2..5], query}` |
| POST | `/api/user/interaction` | Record `view` / `chat` / `compare` / `like` / `share` |
| GET | `/api/user/{id}/preferences`, `/api/user/{id}/recommendations` | Profile summary and ranked picks |
| POST / GET | `/api/onboarding`, `/api/onboarding/check/{id}` | Save or read questionnaire answers |
| POST / GET | `/api/youtube/search`, `/api/youtube/analyze`, `/api/youtube/status` | Video search, analysis and dependency check |
| WS | `/ws/feed` | `{"type": "new_article", ...}` pushes (`ping` → `pong`) |
| WS | `/ws/chat/{session}` | Chat over a socket: `{query, type?, article_id?, article_ids?}` |

Example:

```bash
curl -X POST "http://127.0.0.1:8000/api/news/fetch?category=Technology&num_results=5"
curl -X POST http://127.0.0.1:8000/api/chat/query \
  -H "Content-Type: application/json" -d '{"query": "What is new in electric vehicles?"}'
```

## Deployment

The API is a standard ASGI app. In production:

```bash
pip install -r requirements.txt
npm --prefix frontend/onboarding-app ci && npm run build
HOST=0.0.0.0 PORT=8000 python app.py --stream
```

- Put it behind a TLS-terminating reverse proxy that forwards WebSocket upgrades for `/ws/*`.
- Run one worker. Articles, profiles and the ingestion loop live in process memory, so
  several workers would each hold a different index.
- Set `CORS_ORIGINS` to your real origin and leave `ADMIN_TOKEN` unset unless you need it.
- For durable onboarding data, point `DATABASE_URL` at Postgres and install a driver (e.g.
  `pip install psycopg2-binary`).
- Run the Pathway server as a second process next to the API and set `PATHWAY_RETRIEVER_URL`.

## Project structure

```
├── app.py                      # CLI entry point (uvicorn + optional background streaming)
├── config.py                   # Settings from environment variables
├── utils.py                    # Tokenising, topic parsing, UTC helpers
├── api/
│   ├── main.py                 # FastAPI app factory, routes, WebSockets
│   ├── services.py             # Component wiring and the ingestion workflow
│   ├── schemas.py              # Validated request models
│   ├── database.py             # SQLAlchemy engine/session helper
│   └── db_models.py            # Onboarding table
├── connectors/
│   ├── news_connector.py       # Serper news discovery
│   ├── article_scraper.py      # news-please extraction + topic tagging
│   └── youtube_analyzer.py     # Video search, download, Whisper, LLM analysis
├── rag/
│   ├── article_store.py        # Shared in-memory store + keyword retriever
│   └── rag_engine.py           # Global / article / comparison RAG, Pathway client
├── user/
│   ├── user_profile.py         # Interaction tracking and preference scores
│   └── recommendation_engine.py# Personalised feed, related articles, comparisons
├── pipeline/
│   └── document_pipeline.py    # Pathway streaming connector + DocumentStore server
├── frontend/
│   ├── index.html, app.js, styles.css   # Main web UI (served at /)
│   └── onboarding-app/                  # React + Vite questionnaire (served at /onboarding/)
├── tests/                      # pytest suite
├── docs/hackathon-brief.md     # Original hackathon problem statement
├── requirements*.txt           # Runtime, dev and optional YouTube dependencies
└── pyproject.toml              # Ruff and pytest configuration
```

## Limitations

- The API's article index and user profiles are not persisted across restarts.
- Topic tagging is keyword-based, not NLP-based.
- There is no authentication. User IDs are anonymous IDs generated in the browser and kept in
  `localStorage`.
- Some publishers block scraping, so not every discovered URL yields an article.

## Credits

Originally built by the DataQuest 2026 team (IIT Kharagpur) for the Megalith 2026 "Live AI" hackathon.

---

Built with [Pathway](https://pathway.com), the live data framework.
