"""Request models for the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from user.user_profile import INTERACTION_TYPES

UserId = Field(None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
RequiredUserId = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
Query = Field(..., min_length=1, max_length=2000)

InteractionType = Literal[INTERACTION_TYPES]  # type: ignore[valid-type]


class ChatQueryRequest(BaseModel):
    query: str = Query
    user_id: str | None = UserId
    category: str | None = Field(None, max_length=50)


class ArticleChatRequest(BaseModel):
    query: str = Query
    user_id: str | None = UserId
    expand_context: bool = True


class ComparisonRequest(BaseModel):
    article_ids: list[str] = Field(..., min_length=2, max_length=5)
    query: str = Query
    user_id: str | None = UserId


class InteractionRequest(BaseModel):
    user_id: str = RequiredUserId
    article_id: str = Field(..., min_length=1, max_length=64)
    interaction_type: InteractionType


class YouTubeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=300)
    num_results: int = Field(5, ge=1, le=10)


class YouTubeAnalyzeRequest(BaseModel):
    video_url: str = Field(..., max_length=300)
    article_title: str = Field(..., min_length=1, max_length=500)
    article_content: str | None = Field(None, max_length=20000)
    video_title: str | None = Field(None, max_length=500)


class OnboardingRequest(BaseModel):
    user_id: str = RequiredUserId
    categories: list[str] = Field(..., min_length=1, max_length=20)
    reading_depth: str = Field(..., max_length=50)
    daily_time: str = Field(..., max_length=50)
    content_formats: list[str] = Field(..., max_length=20)
    primary_reason: str = Field(..., max_length=100)
    industry: str = Field(..., max_length=100)
    regions: list[str] = Field(..., max_length=20)
    ai_summary_preference: str = Field(..., max_length=50)
    importance_timely: int = Field(..., ge=1, le=5)
    importance_accurate: int = Field(..., ge=1, le=5)
    importance_engaging: int = Field(..., ge=1, le=5)
