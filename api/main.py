"""
FastAPI application: REST + WebSocket API and static frontend for the Live AI News platform.

Run from the repository root::

    uvicorn api.main:app --reload
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from api.db_models import UserOnboarding
from api.schemas import (
    ArticleChatRequest,
    ChatQueryRequest,
    ComparisonRequest,
    InteractionRequest,
    OnboardingRequest,
    YouTubeAnalyzeRequest,
    YouTubeSearchRequest,
)
from api.services import Services
from config import PROJECT_ROOT, Config
from connectors.news_connector import MissingAPIKeyError
from connectors.youtube_analyzer import dependency_status, extract_video_id
from utils import utcnow_iso

logger = logging.getLogger(__name__)

APP_VERSION = "1.1.0"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
ONBOARDING_DIST = FRONTEND_DIR / "onboarding-app" / "dist"
USER_ID_PATTERN = r"^[A-Za-z0-9_.:-]{1,64}$"


def get_services(request: Request) -> Services:
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(get_services)]


def require_admin(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    if not Config.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Admin endpoints are disabled (ADMIN_TOKEN not set)")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, Config.ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid admin token")


def create_app(services: Services | None = None, enable_streaming: bool | None = None) -> FastAPI:
    """Application factory. Tests pass their own ``services``; production builds the defaults."""
    streaming = Config.NEWS_STREAMING_ENABLED if enable_streaming is None else enable_streaming

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = services or Services.create()
        svc.db.create_tables()
        app.state.services = svc
        stream_task: asyncio.Task | None = None
        if streaming:
            if svc.news.api_key:
                stream_task = asyncio.create_task(svc.stream_forever())
                logger.info("Background news streaming enabled")
            else:
                logger.warning("NEWS_STREAMING_ENABLED is set but SERPER_API_KEY is missing; not streaming")
        logger.info("Live AI News API ready (LLM configured: %s)", svc.rag.llm_configured)
        yield
        if stream_task:
            stream_task.cancel()
            await asyncio.gather(stream_task, return_exceptions=True)
        svc.shutdown()

    app = FastAPI(
        title="Live AI News Platform",
        description="Real-time news ingestion, personalised feeds and RAG chat over live articles.",
        version=APP_VERSION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=Config.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Admin-Token"],
    )

    @app.exception_handler(MissingAPIKeyError)
    async def _missing_key(_: Request, exc: MissingAPIKeyError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    _register_routes(app)
    return app


def _article_or_404(services: Services, article_id: str) -> dict[str, Any]:
    article = services.store.get(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


def _feed_item(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "article_id": article["article_id"],
        "title": article.get("title"),
        "category": article.get("category"),
        "source": article.get("source"),
        "url": article.get("url"),
        "topics": article.get("topics", []),
        "publish_date": article.get("publish_date"),
        "description": article.get("description"),
        "image_url": article.get("image_url"),
    }


def _register_routes(app: FastAPI) -> None:
    # ------------------------------------------------------------------ pages
    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    if ONBOARDING_DIST.exists():
        app.mount("/onboarding", StaticFiles(directory=ONBOARDING_DIST, html=True), name="onboarding")
    else:

        @app.get("/onboarding", include_in_schema=False)
        async def onboarding_not_built() -> JSONResponse:
            return JSONResponse(
                status_code=404,
                content={"detail": "Onboarding app not built. Run `npm run build` (or use `npm run onboarding`)."},
            )

    @app.get("/", include_in_schema=False)
    async def root():
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Live AI News Platform API", "docs": "/docs"}

    # ----------------------------------------------------------------- health
    @app.get("/health", tags=["system"])
    async def health_check() -> dict[str, Any]:
        return {"status": "healthy", "timestamp": utcnow_iso(), "version": APP_VERSION}

    @app.get("/api/stats", tags=["system"])
    async def get_stats(services: ServicesDep) -> dict[str, Any]:
        return {
            "rag_engine": services.rag.get_stats(),
            "recommendation_engine": services.recommendations.get_stats(),
            "profile_manager": services.profiles.get_stats(),
            "news_connector": {k: v for k, v in services.news.get_stats().items() if k != "categories"},
            "timestamp": utcnow_iso(),
        }

    # ------------------------------------------------------------------- news
    @app.get("/api/news/feed", tags=["news"])
    async def get_news_feed(
        services: ServicesDep,
        user_id: Annotated[str | None, Query(pattern=USER_ID_PATTERN)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        exclude_viewed: bool = False,
    ) -> dict[str, Any]:
        """Latest articles; ranked for the user when ``user_id`` is given."""
        if not user_id:
            articles = [_feed_item(a) for a in services.store.all()[:limit]]
            return {"personalized": False, "articles": articles, "count": len(articles)}

        recs = services.recommendations.get_personalized_feed(user_id, limit=limit, exclude_viewed=exclude_viewed)
        articles = []
        for rec in recs:
            article = services.store.get(rec.article_id) or {"article_id": rec.article_id}
            articles.append({**_feed_item(article), "relevance_score": rec.score, "reasons": rec.reasons})
        return {"user_id": user_id, "personalized": True, "articles": articles, "count": len(articles)}

    @app.get("/api/news/article/{article_id}", tags=["news"])
    async def get_article(
        article_id: str,
        services: ServicesDep,
        user_id: Annotated[str | None, Query(pattern=USER_ID_PATTERN)] = None,
    ) -> dict[str, Any]:
        article = _article_or_404(services, article_id)
        if user_id:
            services.profiles.track_interaction(user_id, article, "view")

        related = services.recommendations.get_related_articles(article_id, limit=5)
        comparison = services.recommendations.suggest_comparison(article_id)
        return {
            "article": article,
            "related_articles": [{"article_id": r.article_id, "title": r.title, "reasons": r.reasons} for r in related],
            "comparison_suggestion": (
                {
                    "article_ids": comparison.article_ids,
                    "titles": comparison.titles,
                    "prompt": comparison.comparison_prompt,
                }
                if comparison
                else None
            ),
        }

    @app.get("/api/news/search", tags=["news"])
    async def search_news(
        services: ServicesDep,
        query: Annotated[str, Query(min_length=1, max_length=300)],
        category: str | None = None,
        limit: Annotated[int, Query(ge=1, le=50)] = 10,
    ) -> dict[str, Any]:
        results = [_feed_item(a) for a in services.store.search(query, top_k=limit, category=category)]
        return {"query": query, "category": category, "results": results, "count": len(results)}

    @app.post("/api/news/fetch", tags=["news"])
    async def fetch_news(
        services: ServicesDep,
        category: Annotated[str | None, Query(max_length=50)] = None,
        num_results: Annotated[int, Query(ge=1, le=20)] = 10,
    ) -> dict[str, Any]:
        """Fetch fresh URLs from Serper (one category, or all), scrape and index them."""
        if category:
            results = await services.news.search_category(category, num_results=num_results)
        else:
            results = await services.news.fetch_all_categories()
        if not results:
            return {"message": "No new articles found", "count": 0, "articles": []}

        articles = await services.ingest(results)
        return {
            "message": f"Fetched and indexed {len(articles)} new articles",
            "count": len(articles),
            "articles": [{"title": a.title, "article_id": a.article_id} for a in articles],
        }

    # ------------------------------------------------------------------- chat
    @app.post("/api/chat/query", tags=["chat"])
    async def chat_global_query(body: ChatQueryRequest, services: ServicesDep) -> dict[str, Any]:
        response = await services.rag.query_global(query=body.query, category=body.category)
        return response.to_dict()

    @app.post("/api/chat/article/{article_id}", tags=["chat"])
    async def chat_with_article(article_id: str, body: ArticleChatRequest, services: ServicesDep) -> dict[str, Any]:
        article = _article_or_404(services, article_id)
        if body.user_id:
            services.profiles.track_interaction(body.user_id, article, "chat")
        response = await services.rag.query_article(body.query, article_id, expand_context=body.expand_context)
        return response.to_dict()

    @app.post("/api/chat/compare", tags=["chat"])
    async def chat_compare_articles(body: ComparisonRequest, services: ServicesDep) -> dict[str, Any]:
        articles = services.store.get_many(body.article_ids)
        if not articles:
            raise HTTPException(status_code=404, detail="None of the specified articles were found")
        if body.user_id:
            services.profiles.track_comparison(body.user_id, articles)
        response = await services.rag.query_comparison(body.query, body.article_ids)
        return response.to_dict()

    # ------------------------------------------------------------------- user
    @app.post("/api/user/interaction", tags=["user"])
    async def track_user_interaction(body: InteractionRequest, services: ServicesDep) -> dict[str, Any]:
        article = _article_or_404(services, body.article_id)
        changes = services.profiles.track_interaction(body.user_id, article, body.interaction_type)
        return {"tracked": True, "changes": changes}

    @app.get("/api/user/{user_id}/preferences", tags=["user"])
    async def get_user_preferences(user_id: str, services: ServicesDep) -> dict[str, Any]:
        summary = services.profiles.get_user_preferences_summary(user_id)
        if summary is None:
            raise HTTPException(status_code=404, detail="User not found")
        return summary

    @app.get("/api/user/{user_id}/recommendations", tags=["user"])
    async def get_user_recommendations(
        user_id: str, services: ServicesDep, limit: Annotated[int, Query(ge=1, le=50)] = 10
    ) -> dict[str, Any]:
        recs = services.recommendations.get_personalized_feed(user_id, limit=limit)
        return {
            "user_id": user_id,
            "recommendations": [
                {"article_id": r.article_id, "title": r.title, "score": r.score, "reasons": r.reasons} for r in recs
            ],
        }

    # ------------------------------------------------------------- onboarding
    @app.post("/api/onboarding", tags=["onboarding"])
    async def save_onboarding(body: OnboardingRequest, services: ServicesDep) -> dict[str, Any]:
        """Store questionnaire answers once per user and seed their category preferences."""
        with services.db.session() as session:
            existing = session.scalar(select(UserOnboarding).where(UserOnboarding.user_id == body.user_id))
            if existing:
                message = "Onboarding already completed"
            else:
                session.add(UserOnboarding(**body.model_dump()))
                message = "Onboarding completed successfully"
        services.profiles.seed_preferences(body.user_id, body.categories)
        return {"success": True, "message": message, "user_id": body.user_id}

    @app.get("/api/onboarding/check/{user_id}", tags=["onboarding"])
    async def check_onboarding(user_id: str, services: ServicesDep) -> dict[str, Any]:
        with services.db.session() as session:
            record = session.scalar(select(UserOnboarding).where(UserOnboarding.user_id == user_id))
            data = record.to_dict() if record else None
        # Restore seeded preferences after a server restart (profiles live in memory).
        if data and not services.profiles.get_user(user_id):
            services.profiles.seed_preferences(user_id, data["categories"] or [])
        return {"completed": data is not None, "data": data}

    # ---------------------------------------------------------------- youtube
    @app.post("/api/youtube/search", tags=["youtube"])
    async def search_youtube_videos(body: YouTubeSearchRequest, services: ServicesDep) -> dict[str, Any]:
        results = await services.youtube.search_youtube_videos(body.query, num_results=body.num_results)
        return {"query": body.query, "videos": [r.to_dict() for r in results], "count": len(results)}

    @app.post("/api/youtube/analyze", tags=["youtube"])
    async def analyze_youtube_video(body: YouTubeAnalyzeRequest, services: ServicesDep) -> dict[str, Any]:
        """Download, transcribe and analyse a YouTube video. Can take a few minutes."""
        if not extract_video_id(body.video_url):
            raise HTTPException(status_code=422, detail="video_url must be a YouTube video URL")
        deps = dependency_status()
        if not deps["ffmpeg"] or not deps["whisper"]:
            raise HTTPException(
                status_code=503,
                detail="Video analysis needs ffmpeg and the packages in requirements-youtube.txt",
            )
        result = await services.youtube.analyze_video(
            youtube_url=body.video_url,
            article_title=body.article_title,
            article_content=body.article_content,
            video_title=body.video_title,
        )
        if not result:
            raise HTTPException(status_code=502, detail="Could not download or transcribe this video")
        return result.to_dict()

    @app.get("/api/youtube/status", tags=["youtube"])
    async def youtube_analyzer_status() -> dict[str, Any]:
        deps = dependency_status()
        ready = deps["ffmpeg"] and deps["whisper"] and (deps["pytubefix"] or deps["yt_dlp"])
        return {
            "ready": ready,
            "dependencies": deps,
            "message": "All dependencies ready"
            if ready
            else "Missing dependencies: install ffmpeg and `pip install -r requirements-youtube.txt`",
        }

    # -------------------------------------------------------------- websocket
    @app.websocket("/ws/feed")
    async def websocket_feed(websocket: WebSocket) -> None:
        """Pushes ``{"type": "new_article", ...}`` messages as articles are indexed."""
        manager = websocket.app.state.services.ws
        await manager.connect(websocket, "feed")
        try:
            while True:
                if await websocket.receive_text() == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            manager.disconnect(websocket, "feed")

    @app.websocket("/ws/chat/{session_id}")
    async def websocket_chat(websocket: WebSocket, session_id: str) -> None:
        services: Services = websocket.app.state.services
        await services.ws.connect(websocket, "chat")
        try:
            while True:
                data = await websocket.receive_json()
                query = str(data.get("query", "")).strip()[:2000]
                if not query:
                    await websocket.send_json({"session_id": session_id, "error": "query is required"})
                    continue
                if data.get("type") == "article" and data.get("article_id"):
                    response = await services.rag.query_article(query, str(data["article_id"]))
                elif data.get("type") == "compare" and data.get("article_ids"):
                    response = await services.rag.query_comparison(query, [str(a) for a in data["article_ids"]][:5])
                else:
                    response = await services.rag.query_global(query)
                await websocket.send_json({"session_id": session_id, "response": response.to_dict()})
        except WebSocketDisconnect:
            services.ws.disconnect(websocket, "chat")
        except ValueError:
            await websocket.close(code=1003)
            services.ws.disconnect(websocket, "chat")

    # ------------------------------------------------------------------ admin
    @app.post("/api/admin/clear-cache", tags=["admin"], dependencies=[Depends(require_admin)])
    async def clear_caches(services: ServicesDep) -> dict[str, str]:
        services.scraper.clear_cache()
        return {"message": "Caches cleared"}


app = create_app()
