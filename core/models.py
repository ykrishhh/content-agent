"""
Data models for the content agent.

All models are plain dataclasses — no external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Platform(str, Enum):
    """Supported publishing platforms."""
    BLOG = "blog"
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    EMAIL = "email"
    MEDIUM = "medium"
    SUBSTACK = "substack"


class ContentStatus(str, Enum):
    """Lifecycle states of a content piece."""
    IDEA = "idea"
    RESEARCHING = "researching"
    DRAFT = "draft"
    OPTIMIZING = "optimizing"
    READY = "ready"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass
class Topic:
    """A researched topic ready for content generation."""
    id: Optional[int] = None
    title: str = ""
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    trending_score: float = 0.0
    competition_level: str = "medium"  # low, medium, high
    suggested_angle: str = ""
    category: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = ContentStatus.IDEA.value

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "keywords": self.keywords,
            "sources": self.sources,
            "trending_score": self.trending_score,
            "competition_level": self.competition_level,
            "suggested_angle": self.suggested_angle,
            "category": self.category,
            "created_at": self.created_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Topic:
        return cls(
            id=data.get("id"),
            title=data.get("title", ""),
            description=data.get("description", ""),
            keywords=data.get("keywords", []),
            sources=data.get("sources", []),
            trending_score=data.get("trending_score", 0.0),
            competition_level=data.get("competition_level", "medium"),
            suggested_angle=data.get("suggested_angle", ""),
            category=data.get("category", ""),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            status=data.get("status", ContentStatus.IDEA.value),
        )


@dataclass
class Post:
    """A content piece generated for a specific platform."""
    id: Optional[int] = None
    topic_id: Optional[int] = None
    platform: str = Platform.BLOG.value
    title: str = ""
    body: str = ""
    meta_title: str = ""
    meta_description: str = ""
    tags: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    slug: str = ""
    word_count: int = 0
    reading_time_min: int = 0
    seo_score: float = 0.0
    status: str = ContentStatus.DRAFT.value
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    published_at: Optional[str] = None
    url: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "topic_id": self.topic_id,
            "platform": self.platform,
            "title": self.title,
            "body": self.body,
            "meta_title": self.meta_title,
            "meta_description": self.meta_description,
            "tags": self.tags,
            "hashtags": self.hashtags,
            "slug": self.slug,
            "word_count": self.word_count,
            "reading_time_min": self.reading_time_min,
            "seo_score": self.seo_score,
            "status": self.status,
            "created_at": self.created_at,
            "published_at": self.published_at,
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Post:
        return cls(
            id=data.get("id"),
            topic_id=data.get("topic_id"),
            platform=data.get("platform", Platform.BLOG.value),
            title=data.get("title", ""),
            body=data.get("body", ""),
            meta_title=data.get("meta_title", ""),
            meta_description=data.get("meta_description", ""),
            tags=data.get("tags", []),
            hashtags=data.get("hashtags", []),
            slug=data.get("slug", ""),
            word_count=data.get("word_count", 0),
            reading_time_min=data.get("reading_time_min", 0),
            seo_score=data.get("seo_score", 0.0),
            status=data.get("status", ContentStatus.DRAFT.value),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            published_at=data.get("published_at"),
            url=data.get("url"),
        )


@dataclass
class ScheduleSlot:
    """A scheduled publishing slot."""
    id: Optional[int] = None
    post_id: Optional[int] = None
    platform: str = Platform.BLOG.value
    scheduled_at: str = ""
    timezone: str = "UTC"
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "post_id": self.post_id,
            "platform": self.platform,
            "scheduled_at": self.scheduled_at,
            "timezone": self.timezone,
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ScheduleSlot:
        return cls(
            id=data.get("id"),
            post_id=data.get("post_id"),
            platform=data.get("platform", Platform.BLOG.value),
            scheduled_at=data.get("scheduled_at", ""),
            timezone=data.get("timezone", "UTC"),
            status=data.get("status", "pending"),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
        )


@dataclass
class AnalyticsRecord:
    """Performance analytics for a published post."""
    id: Optional[int] = None
    post_id: Optional[int] = None
    platform: str = ""
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    clicks: int = 0
    engagement_rate: float = 0.0
    recorded_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "post_id": self.post_id,
            "platform": self.platform,
            "views": self.views,
            "likes": self.likes,
            "comments": self.comments,
            "shares": self.shares,
            "clicks": self.clicks,
            "engagement_rate": self.engagement_rate,
            "recorded_at": self.recorded_at,
        }
