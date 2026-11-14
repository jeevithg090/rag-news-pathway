"""
YouTube video analyser (optional feature).

Pipeline: Serper video search -> audio download (pytubefix, falling back to yt-dlp) ->
Whisper transcription -> LLM analysis of the transcript against a news article.

The heavy dependencies (``openai-whisper``, ``pytubefix``, ``yt-dlp``) and ``ffmpeg`` are
only needed for :meth:`YouTubeAnalyzer.analyze_video`; they are listed in
``requirements-youtube.txt``.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import logging
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from config import Config
from connectors.news_connector import MissingAPIKeyError

logger = logging.getLogger(__name__)

YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"})
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
TRANSCRIPT_PROMPT_CHARS = 4000
MAX_KEY_POINTS = 5


@dataclass
class YouTubeSearchResult:
    video_id: str
    url: str
    title: str
    channel: str
    description: str
    thumbnail: str | None
    duration: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VideoAnalysisResult:
    video_url: str
    video_title: str
    transcript: str
    analysis: str
    key_points: list[str]
    sentiment: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_video_id(url: str) -> str | None:
    """Return the 11-character video ID of a YouTube URL, or ``None`` if it is not one."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").lower() not in YOUTUBE_HOSTS:
        return None

    host = parsed.hostname.lower()
    candidate: str | None = None
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path == "/watch":
        candidate = parse_qs(parsed.query).get("v", [None])[0]
    elif parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
        candidate = parsed.path.split("/")[2]
    return candidate if candidate and _VIDEO_ID_RE.match(candidate) else None


def extract_key_points(analysis: str, limit: int = MAX_KEY_POINTS) -> list[str]:
    """Pull bullet / numbered list items out of an LLM analysis."""
    points: list[str] = []
    for line in analysis.splitlines():
        match = re.match(r"^\s*(?:[-*•]|\d+[.)])\s+(.*\S)", line)
        if not match:
            continue
        point = match.group(1).strip().strip("*").strip()
        if point:
            points.append(point)
        if len(points) >= limit:
            break
    return points


def detect_sentiment(analysis: str) -> str:
    """Very rough sentiment label derived from the analysis wording."""
    match = re.search(r"sentiment\W{0,10}(positive|negative|neutral|mixed)", analysis, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower()
    lowered = analysis.lower()
    if any(word in lowered for word in ("positive", "optimistic", "bullish", "favorable")):
        return "positive"
    if any(word in lowered for word in ("negative", "pessimistic", "bearish")):
        return "negative"
    return "neutral"


def dependency_status() -> dict[str, bool]:
    return {
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "whisper": importlib.util.find_spec("whisper") is not None,
        "pytubefix": importlib.util.find_spec("pytubefix") is not None,
        "yt_dlp": importlib.util.find_spec("yt_dlp") is not None,
    }


class YouTubeAnalyzer:
    def __init__(
        self,
        serper_key: str | None = None,
        openrouter_key: str | None = None,
        whisper_model: str | None = None,
        cache_dir: Path | None = None,
    ):
        self.serper_key = serper_key or Config.SERPER_API_KEY
        self.openrouter_key = openrouter_key or Config.OPENROUTER_API_KEY
        self.whisper_model_name = whisper_model or Config.WHISPER_MODEL
        self.cache_dir = cache_dir or (Config.CACHE_DIR / "youtube")
        self._whisper_model = None

    # ------------------------------------------------------------ search
    async def _serper_videos(self, client: httpx.AsyncClient, query: str, num: int) -> list[dict]:
        response = await client.post(
            Config.SERPER_VIDEOS_URL,
            headers={"X-API-KEY": self.serper_key, "Content-Type": "application/json"},
            json={"q": query, "num": num},
        )
        response.raise_for_status()
        return response.json().get("videos", [])

    async def search_youtube_videos(self, query: str, num_results: int = 5) -> list[YouTubeSearchResult]:
        """Search YouTube via Serper, retrying with shorter queries if nothing is found."""
        if not self.serper_key:
            raise MissingAPIKeyError("SERPER_API_KEY is not configured")

        words = query.split()
        attempts = [f"{query} youtube"]
        if len(words) > 6:
            attempts.append(f"{' '.join(words[:6])} youtube")
        if len(words) > 3:
            attempts.append(f"{' '.join(words[:3])} news youtube")

        videos: list[dict] = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for attempt in attempts:
                    videos = await self._serper_videos(client, attempt, num_results)
                    if videos:
                        break
        except httpx.HTTPError as exc:
            logger.error("Serper video search failed for %r: %s", query, exc)
            return []

        results = []
        for video in videos:
            link = video.get("link", "")
            video_id = extract_video_id(link)
            if not video_id:
                continue  # skip non-YouTube hits so the UI only offers analysable videos
            results.append(
                YouTubeSearchResult(
                    video_id=video_id,
                    url=link,
                    title=video.get("title", ""),
                    channel=video.get("channel", ""),
                    description=video.get("snippet", ""),
                    thumbnail=video.get("imageUrl"),
                    duration=video.get("duration"),
                )
            )
            if len(results) >= num_results:
                break
        return results

    # ---------------------------------------------------------- download
    def _download_with_pytubefix(self, url: str, target: Path) -> Path | None:
        from pytubefix import YouTube

        for client_name in ("WEB", "ANDROID", "IOS"):
            try:
                yt = YouTube(url, client=client_name)
                yt.check_availability()
                stream = yt.streams.get_audio_only()
                if not stream:
                    continue
                raw_path = Path(stream.download(output_path=str(self.cache_dir), filename=f"{target.stem}_raw"))
                result = subprocess.run(
                    ["ffmpeg", "-i", str(raw_path), "-vn", "-acodec", "libmp3lame", "-q:a", "2", "-y", str(target)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    logger.warning("ffmpeg conversion failed; using raw audio file")
                    return raw_path
                raw_path.unlink(missing_ok=True)
                return target
            except Exception as exc:  # pytubefix raises many client-specific errors
                logger.warning("pytubefix client %s failed: %s", client_name, exc)
        return None

    def _download_with_ytdlp(self, url: str, target: Path) -> Path | None:
        import yt_dlp

        options = {
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
            "outtmpl": str(target.with_suffix(".%(ext)s")),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
        return target if target.exists() else None

    async def download_audio(self, youtube_url: str) -> str | None:
        """Download a video's audio track as MP3 (cached on disk). Returns its path."""
        if not extract_video_id(youtube_url):
            raise ValueError("Not a valid YouTube video URL")

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        target = self.cache_dir / f"{hashlib.sha256(youtube_url.encode()).hexdigest()[:16]}.mp3"
        if target.exists():
            return str(target)

        loop = asyncio.get_running_loop()
        for downloader in (self._download_with_pytubefix, self._download_with_ytdlp):
            try:
                path = await loop.run_in_executor(None, downloader, youtube_url, target)
            except ImportError as exc:
                logger.warning("Downloader unavailable: %s", exc)
                continue
            except Exception:
                logger.exception("Audio download failed with %s", downloader.__name__)
                continue
            if path and os.path.exists(path):
                return str(path)
        return None

    # -------------------------------------------------------- transcribe
    async def transcribe_audio(self, audio_path: str) -> str | None:
        def _transcribe() -> str:
            if self._whisper_model is None:
                import whisper

                self._whisper_model = whisper.load_model(self.whisper_model_name)
            return self._whisper_model.transcribe(audio_path)["text"]

        try:
            return await asyncio.get_running_loop().run_in_executor(None, _transcribe)
        except Exception:
            logger.exception("Transcription failed")
            return None

    # ----------------------------------------------------------- analyse
    async def analyze_transcript(
        self, transcript: str, article_title: str, article_content: str | None = None
    ) -> dict[str, Any]:
        if not self.openrouter_key:
            raise MissingAPIKeyError("OPENROUTER_API_KEY is not configured")

        context = f"News article: {article_title}"
        if article_content:
            context += f"\n\nArticle summary: {article_content[:500]}"

        prompt = f"""Analyse this YouTube video transcript in relation to the news article.

{context}

Video transcript:
{transcript[:TRANSCRIPT_PROMPT_CHARS]}

Provide:
1. **Summary**: the video's main points (2-3 sentences)
2. **Video perspective**: the creator's stance on this news
3. **Key points**: 3-5 bullet points
4. **Sentiment**: positive, negative, neutral or mixed
5. **Additional context**: anything the video adds that the article does not"""

        try:
            async with httpx.AsyncClient(timeout=Config.LLM_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{Config.LLM_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {self.openrouter_key}", "X-Title": "Live AI News"},
                    json={
                        "model": Config.LLM_MODEL,
                        "messages": [
                            {"role": "system", "content": "You are an expert news and media analyst."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.7,
                        "max_tokens": 1500,
                    },
                )
                response.raise_for_status()
                analysis = response.json()["choices"][0]["message"]["content"] or ""
        except (httpx.HTTPError, KeyError, IndexError):
            logger.exception("Transcript analysis failed")
            return {"analysis": "Analysis failed. Please try again.", "key_points": [], "sentiment": "unknown"}

        return {
            "analysis": analysis,
            "key_points": extract_key_points(analysis),
            "sentiment": detect_sentiment(analysis),
        }

    async def analyze_video(
        self,
        youtube_url: str,
        article_title: str,
        article_content: str | None = None,
        video_title: str | None = None,
    ) -> VideoAnalysisResult | None:
        audio_path = await self.download_audio(youtube_url)
        if not audio_path:
            return None
        transcript = await self.transcribe_audio(audio_path)
        if not transcript:
            return None
        result = await self.analyze_transcript(transcript, article_title, article_content)
        return VideoAnalysisResult(
            video_url=youtube_url,
            video_title=video_title or article_title,
            transcript=transcript,
            analysis=result["analysis"],
            key_points=result["key_points"],
            sentiment=result["sentiment"],
        )
