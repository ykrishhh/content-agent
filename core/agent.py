"""
ContentAgent — the main orchestrator.

Ties together research, generation, optimization, scheduling,
and publishing into a single top-level interface.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .content_generator import ContentGenerator
from .content_pipeline import ContentPipeline
from .db import DatabaseManager
from .models import (
    ContentStatus,
    Platform,
    Post,
    ScheduleSlot,
    Topic,
)
from .seo_optimizer import SEOOptimizer
from .topic_researcher import TopicResearcher

logger = logging.getLogger("content_agent")

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.json"


class ContentAgent:
    """
    Top-level autonomous content agent.

    Usage::

        agent = ContentAgent()
        posts = agent.research_topic("AI in healthcare")
        agent.publish(posts[0].id)
    """

    def __init__(self, config_path: Optional[str | Path] = None):
        self.config = self._load_config(config_path or DEFAULT_CONFIG_PATH)

        self.db = DatabaseManager(
            db_path=self.config.get("db_path")
        )
        self.researcher = TopicResearcher(
            api_key=self.config.get("api_keys", {}).get("search"),
        )
        self.generator = ContentGenerator(
            sender_name=self.config.get("brand", {}).get("name", "Content Agent"),
        )
        self.optimizer = SEOOptimizer()
        self.pipeline = ContentPipeline(
            db=self.db,
            researcher=self.researcher,
            generator=self.generator,
            optimizer=self.optimizer,
        )

        logger.info("ContentAgent initialized")

    # ------------------------------------------------------------------ Config

    @staticmethod
    def _load_config(path: str | Path) -> dict:
        p = Path(path)
        if p.exists():
            with open(p, "r") as f:
                return json.load(f)
        return {
            "api_keys": {},
            "brand": {"name": "Content Agent"},
            "scheduling": {"timezone": "UTC", "default_offset_hours": 24},
        }

    # --------------------------------------------------------------- Research

    def research_topic(
        self, query: str, niche: str = ""
    ) -> Topic:
        """Research a single topic and persist it."""
        topic = self.researcher.research_topic(query, niche=niche)
        topic = self.db.save_topic(topic)
        logger.info("Researched topic: %s (score=%.2f)", topic.title, topic.trending_score)
        return topic

    def research_trending(self, niche: str, count: int = 10) -> list[Topic]:
        """Fetch trending topics in a niche."""
        topics = self.researcher.fetch_trending(niche, count=count)
        saved = [self.db.save_topic(t) for t in topics]
        logger.info("Found %d trending topics for '%s'", len(saved), niche)
        return saved

    # -------------------------------------------------------------- Generate

    def generate_content(
        self,
        topic_id: int,
        platform: str = Platform.BLOG.value,
    ) -> Post:
        """Generate a post for a given topic and platform."""
        topic = self.db.get_topic(topic_id)
        if topic is None:
            raise ValueError(f"Topic {topic_id} not found")

        post = self.generator.generate(topic, platform=platform)
        post.topic_id = topic.id
        post = self.optimizer.optimize(post)
        post.topic_id = topic.id
        post = self.db.save_post(post)

        logger.info(
            "Generated %s post '%s' (seo=%.1f)",
            platform, post.title, post.seo_score,
        )
        return post

    def generate_all(self, topic_id: int) -> list[Post]:
        """Generate posts for every platform."""
        topic = self.db.get_topic(topic_id)
        if topic is None:
            raise ValueError(f"Topic {topic_id} not found")

        posts = []
        for plat in Platform:
            post = self.generate_content(topic_id, platform=plat.value)
            posts.append(post)
        return posts

    # ---------------------------------------------------------------- Optimize

    def optimize_seo(self, post_id: int) -> Post:
        """Run SEO optimization on an existing post."""
        post = self.db.get_post(post_id)
        if post is None:
            raise ValueError(f"Post {post_id} not found")

        post = self.optimizer.optimize(post)
        post = self.db.save_post(post)
        logger.info("Optimized post %d (score=%.1f)", post_id, post.seo_score)
        return post

    def get_seo_report(self, post_id: int) -> dict:
        """Get detailed SEO analysis for a post."""
        post = self.db.get_post(post_id)
        if post is None:
            raise ValueError(f"Post {post_id} not found")
        return self.optimizer.analyze(post)

    # --------------------------------------------------------------- Schedule

    def schedule_post(
        self, post_id: int, scheduled_at: str, timezone: str = "UTC"
    ) -> ScheduleSlot:
        """Schedule a post for publishing."""
        post = self.db.get_post(post_id)
        if post is None:
            raise ValueError(f"Post {post_id} not found")

        post.status = ContentStatus.SCHEDULED.value
        self.db.save_post(post)

        slot = ScheduleSlot(
            post_id=post_id,
            platform=post.platform,
            scheduled_at=scheduled_at,
            timezone=timezone,
        )
        slot = self.db.save_schedule(slot)
        logger.info("Scheduled post %d for %s", post_id, scheduled_at)
        return slot

    # -------------------------------------------------------------- Publish

    def publish(self, post_id: int, url: Optional[str] = None) -> Post:
        """Mark a post as published."""
        post = self.db.get_post(post_id)
        if post is None:
            raise ValueError(f"Post {post_id} not found")

        post.status = ContentStatus.PUBLISHED.value
        post.published_at = datetime.utcnow().isoformat()
        post.url = url
        post = self.db.save_post(post)
        logger.info("Published post %d (%s)", post_id, post.platform)
        return post

    # ----------------------------------------------------------- Full run

    def full_run(
        self,
        query: str,
        platforms: Optional[list[str]] = None,
        niche: str = "",
        schedule_offset_hours: int = 24,
    ) -> list[Post]:
        """
        Execute the complete pipeline: research → generate → optimize → schedule.
        Returns all generated posts.
        """
        posts = self.pipeline.run(
            topic_query=query,
            platforms=platforms,
            niche=niche,
            schedule_offset_hours=schedule_offset_hours,
        )
        logger.info("Full run complete: %d posts generated", len(posts))
        return posts

    # ----------------------------------------------------------- Utilities

    def get_pending_schedules(self) -> list[ScheduleSlot]:
        """Return all scheduled slots that are due."""
        return self.db.get_pending_schedules()

    def get_stats(self) -> dict:
        """Aggregate stats on topics and posts."""
        return self.pipeline.get_stats()

    def list_topics(self, status: Optional[str] = None) -> list[Topic]:
        return self.db.list_topics(status=status)

    def list_posts(
        self, status: Optional[str] = None, platform: Optional[str] = None
    ) -> list[Post]:
        return self.db.list_posts(status=status, platform=platform)

    def close(self) -> None:
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
