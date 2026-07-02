"""
Content pipeline — end-to-end content production workflow.

    research → draft → optimize → format → schedule

Takes a topic string, produces platform-specific, SEO-optimized posts.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from .content_generator import ContentGenerator
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


class ContentPipeline:
    """Orchestrates the full content lifecycle from idea to schedule."""

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        researcher: Optional[TopicResearcher] = None,
        generator: Optional[ContentGenerator] = None,
        optimizer: Optional[SEOOptimizer] = None,
    ):
        self.db = db or DatabaseManager()
        self.researcher = researcher or TopicResearcher()
        self.generator = generator or ContentGenerator()
        self.optimizer = optimizer or SEOOptimizer()

    # ----- main pipeline ------------------------------------------------------

    def run(
        self,
        topic_query: str,
        platforms: Optional[list[str]] = None,
        niche: str = "",
        schedule_offset_hours: int = 24,
    ) -> list[Post]:
        """
        Execute the full pipeline:
          1. Research topic
          2. Generate drafts for each platform
          3. Optimize each draft
          4. Persist everything
          5. Create schedule slots
        """
        # 1. Research
        topic = self.researcher.research_topic(topic_query, niche=niche)
        topic = self.db.save_topic(topic)

        # 2. Generate
        target_platforms = platforms or [p.value for p in Platform]
        posts = []
        for plat in target_platforms:
            post = self.generator.generate(topic, platform=plat)
            post.topic_id = topic.id
            posts.append(post)

        # 3. Optimize
        for post in posts:
            post = self.optimizer.optimize(post)
            post.topic_id = topic.id
            post = self.db.save_post(post)
            posts[posts.index(self._find_unsaved(posts, post))] = post

        # 4. Schedule
        base_time = datetime.utcnow() + timedelta(hours=schedule_offset_hours)
        for i, post in enumerate(posts):
            slot = ScheduleSlot(
                post_id=post.id,
                platform=post.platform,
                scheduled_at=(
                    base_time + timedelta(hours=i * 2)
                ).isoformat(),
            )
            self.db.save_schedule(slot)

        # Update topic status
        topic.status = ContentStatus.SCHEDULED.value
        self.db.save_topic(topic)

        return posts

    def run_multi(
        self,
        queries: list[str],
        niche: str = "",
        platforms: Optional[list[str]] = None,
    ) -> list[Post]:
        """Run pipeline for multiple topic queries."""
        all_posts: list[Post] = []
        for q in queries:
            posts = self.run(
                q, platforms=platforms, niche=niche, schedule_offset_hours=24
            )
            all_posts.extend(posts)
        return all_posts

    # ----- status queries -----------------------------------------------------

    def get_ready_posts(self) -> list[Post]:
        """Return posts that are optimized and ready for scheduling."""
        return self.db.list_posts(status=ContentStatus.READY.value)

    def get_scheduled_posts(self) -> list[ScheduleSlot]:
        """Return all pending scheduled slots."""
        return self.db.get_pending_schedules()

    def get_stats(self) -> dict:
        """Summary stats across topics and posts."""
        topic_counts = self.db.count_by_status("topics")
        post_counts = self.db.count_by_status("posts")
        return {
            "topics": topic_counts,
            "posts": post_counts,
            "total_topics": sum(topic_counts.values()),
            "total_posts": sum(post_counts.values()),
        }

    # ----- helpers ------------------------------------------------------------

    @staticmethod
    def _find_unsaved(posts: list[Post], saved: Post) -> Post:
        for p in posts:
            if p.id == saved.id:
                return p
        return saved
