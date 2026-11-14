"""SQLAlchemy models persisted by the API."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from utils import utcnow


class Base(DeclarativeBase):
    pass


class UserOnboarding(Base):
    """One-time onboarding questionnaire answers for a user."""

    __tablename__ = "user_onboarding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    categories: Mapped[list[str]] = mapped_column(JSON)
    reading_depth: Mapped[str] = mapped_column(String(50))
    daily_time: Mapped[str] = mapped_column(String(50))
    content_formats: Mapped[list[str]] = mapped_column(JSON)
    primary_reason: Mapped[str] = mapped_column(String(100))
    industry: Mapped[str] = mapped_column(String(100))
    regions: Mapped[list[str]] = mapped_column(JSON)
    ai_summary_preference: Mapped[str] = mapped_column(String(50))
    importance_timely: Mapped[int] = mapped_column(Integer)
    importance_accurate: Mapped[int] = mapped_column(Integer)
    importance_engaging: Mapped[int] = mapped_column(Integer)

    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "categories": self.categories,
            "reading_depth": self.reading_depth,
            "daily_time": self.daily_time,
            "content_formats": self.content_formats,
            "primary_reason": self.primary_reason,
            "industry": self.industry,
            "regions": self.regions,
            "ai_summary_preference": self.ai_summary_preference,
            "importance_timely": self.importance_timely,
            "importance_accurate": self.importance_accurate,
            "importance_engaging": self.importance_engaging,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
