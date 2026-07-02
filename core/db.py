"""
SQLite database manager for content persistence.

Handles all CRUD operations for topics, posts, schedules, and analytics.
Database file lives alongside the package (core/content_agent.db).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import (
    AnalyticsRecord,
    ContentStatus,
    Platform,
    Post,
    ScheduleSlot,
    Topic,
)

DB_PATH = Path(__file__).parent / "content_agent.db"


class DatabaseManager:
    """SQLite-backed storage for all content agent data."""

    def __init__(self, db_path: Optional[str | Path] = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS topics (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                title           TEXT NOT NULL,
                description     TEXT DEFAULT '',
                keywords        TEXT DEFAULT '[]',
                sources         TEXT DEFAULT '[]',
                trending_score  REAL DEFAULT 0.0,
                competition_level TEXT DEFAULT 'medium',
                suggested_angle TEXT DEFAULT '',
                category        TEXT DEFAULT '',
                created_at      TEXT NOT NULL,
                status          TEXT DEFAULT 'idea'
            );

            CREATE TABLE IF NOT EXISTS posts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id        INTEGER REFERENCES topics(id),
                platform        TEXT NOT NULL,
                title           TEXT NOT NULL,
                body            TEXT DEFAULT '',
                meta_title      TEXT DEFAULT '',
                meta_description TEXT DEFAULT '',
                tags            TEXT DEFAULT '[]',
                hashtags        TEXT DEFAULT '[]',
                slug            TEXT DEFAULT '',
                word_count      INTEGER DEFAULT 0,
                reading_time_min INTEGER DEFAULT 0,
                seo_score       REAL DEFAULT 0.0,
                status          TEXT DEFAULT 'draft',
                created_at      TEXT NOT NULL,
                published_at    TEXT,
                url             TEXT
            );

            CREATE TABLE IF NOT EXISTS schedules (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id     INTEGER REFERENCES posts(id),
                platform    TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                timezone    TEXT DEFAULT 'UTC',
                status      TEXT DEFAULT 'pending',
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS analytics (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id         INTEGER REFERENCES posts(id),
                platform        TEXT DEFAULT '',
                views           INTEGER DEFAULT 0,
                likes           INTEGER DEFAULT 0,
                comments        INTEGER DEFAULT 0,
                shares          INTEGER DEFAULT 0,
                clicks          INTEGER DEFAULT 0,
                engagement_rate REAL DEFAULT 0.0,
                recorded_at     TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
            CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform);
            CREATE INDEX IF NOT EXISTS idx_schedules_pending
                ON schedules(status, scheduled_at);
        """)
        self.conn.commit()

    # ------------------------------------------------------------------ Topics

    def save_topic(self, topic: Topic) -> Topic:
        """Insert or update a topic. Returns the topic with id set."""
        if topic.id is not None:
            self.conn.execute(
                """UPDATE topics SET title=?, description=?, keywords=?,
                   sources=?, trending_score=?, competition_level=?,
                   suggested_angle=?, category=?, created_at=?, status=?
                   WHERE id=?""",
                (
                    topic.title,
                    topic.description,
                    json.dumps(topic.keywords),
                    json.dumps(topic.sources),
                    topic.trending_score,
                    topic.competition_level,
                    topic.suggested_angle,
                    topic.category,
                    topic.created_at,
                    topic.status,
                    topic.id,
                ),
            )
        else:
            cur = self.conn.execute(
                """INSERT INTO topics
                   (title, description, keywords, sources, trending_score,
                    competition_level, suggested_angle, category, created_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    topic.title,
                    topic.description,
                    json.dumps(topic.keywords),
                    json.dumps(topic.sources),
                    topic.trending_score,
                    topic.competition_level,
                    topic.suggested_angle,
                    topic.category,
                    topic.created_at,
                    topic.status,
                ),
            )
            topic.id = cur.lastrowid
        self.conn.commit()
        return topic

    def get_topic(self, topic_id: int) -> Optional[Topic]:
        row = self.conn.execute(
            "SELECT * FROM topics WHERE id=?", (topic_id,)
        ).fetchone()
        return self._row_to_topic(row) if row else None

    def list_topics(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[Topic]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM topics WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM topics ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_topic(r) for r in rows]

    def delete_topic(self, topic_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM topics WHERE id=?", (topic_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------- Posts

    def save_post(self, post: Post) -> Post:
        if post.id is not None:
            self.conn.execute(
                """UPDATE posts SET topic_id=?, platform=?, title=?, body=?,
                   meta_title=?, meta_description=?, tags=?, hashtags=?,
                   slug=?, word_count=?, reading_time_min=?, seo_score=?,
                   status=?, created_at=?, published_at=?, url=?
                   WHERE id=?""",
                (
                    post.topic_id,
                    post.platform,
                    post.title,
                    post.body,
                    post.meta_title,
                    post.meta_description,
                    json.dumps(post.tags),
                    json.dumps(post.hashtags),
                    post.slug,
                    post.word_count,
                    post.reading_time_min,
                    post.seo_score,
                    post.status,
                    post.created_at,
                    post.published_at,
                    post.url,
                    post.id,
                ),
            )
        else:
            cur = self.conn.execute(
                """INSERT INTO posts
                   (topic_id, platform, title, body, meta_title,
                    meta_description, tags, hashtags, slug, word_count,
                    reading_time_min, seo_score, status, created_at,
                    published_at, url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    post.topic_id,
                    post.platform,
                    post.title,
                    post.body,
                    post.meta_title,
                    post.meta_description,
                    json.dumps(post.tags),
                    json.dumps(post.hashtags),
                    post.slug,
                    post.word_count,
                    post.reading_time_min,
                    post.seo_score,
                    post.status,
                    post.created_at,
                    post.published_at,
                    post.url,
                ),
            )
            post.id = cur.lastrowid
        self.conn.commit()
        return post

    def get_post(self, post_id: int) -> Optional[Post]:
        row = self.conn.execute(
            "SELECT * FROM posts WHERE id=?", (post_id,)
        ).fetchone()
        return self._row_to_post(row) if row else None

    def list_posts(
        self,
        status: Optional[str] = None,
        platform: Optional[str] = None,
        limit: int = 50,
    ) -> list[Post]:
        query = "SELECT * FROM posts WHERE 1=1"
        params: list = []
        if status:
            query += " AND status=?"
            params.append(status)
        if platform:
            query += " AND platform=?"
            params.append(platform)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_post(r) for r in rows]

    def delete_post(self, post_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM posts WHERE id=?", (post_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # -------------------------------------------------------------- Schedules

    def save_schedule(self, slot: ScheduleSlot) -> ScheduleSlot:
        if slot.id is not None:
            self.conn.execute(
                """UPDATE schedules SET post_id=?, platform=?, scheduled_at=?,
                   timezone=?, status=?, created_at=? WHERE id=?""",
                (
                    slot.post_id,
                    slot.platform,
                    slot.scheduled_at,
                    slot.timezone,
                    slot.status,
                    slot.created_at,
                    slot.id,
                ),
            )
        else:
            cur = self.conn.execute(
                """INSERT INTO schedules
                   (post_id, platform, scheduled_at, timezone, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    slot.post_id,
                    slot.platform,
                    slot.scheduled_at,
                    slot.timezone,
                    slot.status,
                    slot.created_at,
                ),
            )
            slot.id = cur.lastrowid
        self.conn.commit()
        return slot

    def get_pending_schedules(self, before: Optional[str] = None) -> list[ScheduleSlot]:
        limit_time = before or datetime.utcnow().isoformat()
        rows = self.conn.execute(
            """SELECT * FROM schedules
               WHERE status='pending' AND scheduled_at <= ?
               ORDER BY scheduled_at ASC""",
            (limit_time,),
        ).fetchall()
        return [self._row_to_schedule(r) for r in rows]

    def mark_schedule_done(self, schedule_id: int) -> None:
        self.conn.execute(
            "UPDATE schedules SET status='done' WHERE id=?", (schedule_id,)
        )
        self.conn.commit()

    # -------------------------------------------------------------- Analytics

    def save_analytics(self, record: AnalyticsRecord) -> AnalyticsRecord:
        cur = self.conn.execute(
            """INSERT INTO analytics
               (post_id, platform, views, likes, comments, shares, clicks,
                engagement_rate, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.post_id,
                record.platform,
                record.views,
                record.likes,
                record.comments,
                record.shares,
                record.clicks,
                record.engagement_rate,
                record.recorded_at,
            ),
        )
        record.id = cur.lastrowid
        self.conn.commit()
        return record

    def get_analytics_for_post(self, post_id: int) -> list[AnalyticsRecord]:
        rows = self.conn.execute(
            "SELECT * FROM analytics WHERE post_id=? ORDER BY recorded_at DESC",
            (post_id,),
        ).fetchall()
        return [self._row_to_analytics(r) for r in rows]

    # ---------------------------------------------------------- Stats helpers

    def count_by_status(self, table: str = "posts") -> dict[str, int]:
        rows = self.conn.execute(
            f"SELECT status, COUNT(*) as cnt FROM {table} GROUP BY status"
        ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}

    # --------------------------------------------------------- Row → Model

    @staticmethod
    def _row_to_topic(row: sqlite3.Row) -> Topic:
        return Topic.from_dict({
            "id": row["id"],
            "title": row["title"],
            "description": row["description"],
            "keywords": json.loads(row["keywords"]),
            "sources": json.loads(row["sources"]),
            "trending_score": row["trending_score"],
            "competition_level": row["competition_level"],
            "suggested_angle": row["suggested_angle"],
            "category": row["category"],
            "created_at": row["created_at"],
            "status": row["status"],
        })

    @staticmethod
    def _row_to_post(row: sqlite3.Row) -> Post:
        return Post.from_dict({
            "id": row["id"],
            "topic_id": row["topic_id"],
            "platform": row["platform"],
            "title": row["title"],
            "body": row["body"],
            "meta_title": row["meta_title"],
            "meta_description": row["meta_description"],
            "tags": json.loads(row["tags"]),
            "hashtags": json.loads(row["hashtags"]),
            "slug": row["slug"],
            "word_count": row["word_count"],
            "reading_time_min": row["reading_time_min"],
            "seo_score": row["seo_score"],
            "status": row["status"],
            "created_at": row["created_at"],
            "published_at": row["published_at"],
            "url": row["url"],
        })

    @staticmethod
    def _row_to_schedule(row: sqlite3.Row) -> ScheduleSlot:
        return ScheduleSlot.from_dict({
            "id": row["id"],
            "post_id": row["post_id"],
            "platform": row["platform"],
            "scheduled_at": row["scheduled_at"],
            "timezone": row["timezone"],
            "status": row["status"],
            "created_at": row["created_at"],
        })

    @staticmethod
    def _row_to_analytics(row: sqlite3.Row) -> AnalyticsRecord:
        return AnalyticsRecord(
            id=row["id"],
            post_id=row["post_id"],
            platform=row["platform"],
            views=row["views"],
            likes=row["likes"],
            comments=row["comments"],
            shares=row["shares"],
            clicks=row["clicks"],
            engagement_rate=row["engagement_rate"],
            recorded_at=row["recorded_at"],
        )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
