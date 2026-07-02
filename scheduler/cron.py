"""Scheduler for AI Content Agent — manages post scheduling and retries."""

import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "content.db"


class Scheduler:
    """Simple scheduler that checks for due posts and triggers the content pipeline."""

    def __init__(
        self,
        check_interval: int = 900,
        on_generate: Optional[Callable[[int], None]] = None,
        on_notify: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Args:
            check_interval: Seconds between checks (default 900 = 15 min)
            on_generate: Callback(topic_id) to generate content
            on_notify: Callback(message) to send notifications
        """
        self.check_interval = check_interval
        self.on_generate = on_generate
        self.on_notify = on_notify
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._retry_count: dict[int, int] = {}
        self.max_retries = 3

    def start(self) -> None:
        """Start the scheduler in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler started (interval=%ds)", self.check_interval)

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Scheduler stopped")

    def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                self._check_and_process()
            except Exception as e:
                logger.error("Scheduler check error: %s", e)
                if self.on_notify:
                    self.on_notify(f"Scheduler error: {e}")

            # Sleep in small increments so we can stop quickly
            for _ in range(self.check_interval):
                if not self._running:
                    return
                time.sleep(1)

    def _check_and_process(self) -> None:
        """Check for due posts and process them."""
        now = datetime.now()
        conn = self._get_db()

        try:
            # Find posts scheduled for now or earlier that are still 'scheduled'
            due_posts = conn.execute(
                """SELECT p.id, p.topic_id, p.title, p.platform, p.scheduled_at
                   FROM posts p
                   WHERE p.status = 'scheduled'
                     AND p.scheduled_at <= ?
                   ORDER BY p.scheduled_at ASC
                   LIMIT 5""",
                (now.isoformat(),),
            ).fetchall()

            if not due_posts:
                return

            logger.info("Found %d due posts", len(due_posts))

            for post in due_posts:
                self._process_post(conn, post, now)

            # Auto-generate content for pending topics
            self._auto_generate_topics(conn, now)

        finally:
            conn.close()

    def _process_post(self, conn: sqlite3.Connection, post: sqlite3.Row, now: datetime) -> None:
        """Process a single due post."""
        post_id = post["id"]

        try:
            # Mark as published (in a real app, this would post to social media)
            conn.execute(
                """UPDATE posts
                   SET status = 'published', published_at = ?
                   WHERE id = ?""",
                (now.isoformat(), post_id),
            )
            conn.commit()

            conn.execute(
                "INSERT INTO activity_log (action, details) VALUES (?, ?)",
                ("post_published", f"Post #{post_id}: {post['title']}"),
            )
            conn.commit()

            self._retry_count.pop(post_id, None)

            notification = (
                f"Post published!\n"
                f"Title: {post['title']}\n"
                f"Platform: {post['platform']}\n"
                f"Time: {now.strftime('%H:%M')}"
            )
            if self.on_notify:
                self.on_notify(notification)

            logger.info("Published post #%d: %s", post_id, post["title"])

        except Exception as e:
            logger.error("Failed to publish post #%d: %s", post_id, e)
            self._handle_retry(conn, post_id, post["title"], str(e))

    def _handle_retry(
        self, conn: sqlite3.Connection, post_id: int, title: str, error: str
    ) -> None:
        """Handle a failed post with retry logic."""
        retries = self._retry_count.get(post_id, 0) + 1
        self._retry_count[post_id] = retries

        if retries >= self.max_retries:
            # Mark as failed after max retries
            conn.execute(
                "UPDATE posts SET status = 'failed' WHERE id = ?",
                (post_id,),
            )
            conn.commit()

            conn.execute(
                "INSERT INTO activity_log (action, details) VALUES (?, ?)",
                ("post_failed", f"Post #{post_id} failed after {retries} attempts: {error}"),
            )
            conn.commit()

            if self.on_notify:
                self.on_notify(f"Post failed: {title}\nAfter {retries} attempts.\nError: {error}")

            logger.error("Post #%d failed permanently: %s", post_id, error)
        else:
            # Schedule retry in 5 minutes
            retry_time = datetime.now() + timedelta(minutes=5)
            conn.execute(
                "UPDATE posts SET scheduled_at = ? WHERE id = ?",
                (retry_time.isoformat(), post_id),
            )
            conn.commit()
            logger.info("Post #%d retry scheduled (attempt %d/%d)", post_id, retries, self.max_retries)

    def _auto_generate_topics(self, conn: sqlite3.Connection, now: datetime) -> None:
        """Auto-generate content for long-pending topics."""
        # Find topics pending for more than 24 hours
        cutoff = (now - timedelta(hours=24)).isoformat()
        stale_topics = conn.execute(
            """SELECT id, title FROM topics
               WHERE status = 'pending' AND created_at <= ?
               LIMIT 1""",
            (cutoff,),
        ).fetchall()

        if stale_topics and self.on_generate:
            topic = stale_topics[0]
            logger.info("Auto-generating content for stale topic: %s", topic["title"])
            try:
                self.on_generate(topic["id"])
            except Exception as e:
                logger.error("Auto-generate failed for topic #%d: %s", topic["id"], e)

    def schedule_post(
        self,
        title: str,
        content: str,
        platform: str = "all",
        topic_id: Optional[int] = None,
        scheduled_at: Optional[str] = None,
    ) -> int:
        """Schedule a new post. Returns the post ID."""
        if not scheduled_at:
            # Default: schedule for next hour
            next_hour = datetime.now().replace(minute=0, second=0) + timedelta(hours=1)
            scheduled_at = next_hour.isoformat()

        conn = self._get_db()
        try:
            cursor = conn.execute(
                """INSERT INTO posts (topic_id, title, content, platform, status, scheduled_at)
                   VALUES (?, ?, ?, ?, 'scheduled', ?)""",
                (topic_id, title, content, platform, scheduled_at),
            )
            conn.commit()
            post_id = cursor.lastrowid

            conn.execute(
                "INSERT INTO activity_log (action, details) VALUES (?, ?)",
                ("post_scheduled", f"Post #{post_id}: {title} at {scheduled_at}"),
            )
            conn.commit()

            logger.info("Scheduled post #%d: %s at %s", post_id, title, scheduled_at)
            return post_id
        finally:
            conn.close()

    def get_due_posts(self) -> list[dict[str, Any]]:
        """Get all posts due for publishing."""
        conn = self._get_db()
        try:
            now = datetime.now()
            rows = conn.execute(
                """SELECT * FROM posts
                   WHERE status = 'scheduled' AND scheduled_at <= ?
                   ORDER BY scheduled_at""",
                (now.isoformat(),),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_upcoming(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get posts scheduled in the next N hours."""
        conn = self._get_db()
        try:
            now = datetime.now()
            future = (now + timedelta(hours=hours)).isoformat()
            rows = conn.execute(
                """SELECT * FROM posts
                   WHERE status = 'scheduled' AND scheduled_at BETWEEN ? AND ?
                   ORDER BY scheduled_at""",
                (now.isoformat(), future),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def _get_db() -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn
