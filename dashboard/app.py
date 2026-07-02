"""Flask web dashboard for AI Content Agent."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "content.db"


def get_db() -> sqlite3.Connection:
    """Get database connection with row factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Initialize database tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            platform TEXT DEFAULT 'all',
            tags TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER,
            title TEXT NOT NULL,
            content TEXT DEFAULT '',
            platform TEXT DEFAULT 'all',
            status TEXT DEFAULT 'draft',
            scheduled_at TIMESTAMP,
            published_at TIMESTAMP,
            engagement_score REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (topic_id) REFERENCES topics(id)
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            details TEXT DEFAULT '',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def log_activity(action: str, details: str = "") -> None:
    """Log an activity."""
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO activity_log (action, details) VALUES (?, ?)",
            (action, details),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# Initialize database on import
init_db()


@app.route("/")
def index() -> str:
    """Dashboard home page."""
    conn = get_db()
    now = datetime.now()

    # Upcoming posts (next 7 days)
    upcoming = conn.execute(
        """SELECT p.*, t.title as topic_title
           FROM posts p LEFT JOIN topics t ON p.topic_id = t.id
           WHERE p.scheduled_at >= ? AND p.status != 'published'
           ORDER BY p.scheduled_at ASC LIMIT 10""",
        (now.isoformat(),),
    ).fetchall()

    # Topic queue
    pending_topics = conn.execute(
        "SELECT COUNT(*) as cnt FROM topics WHERE status = 'pending'"
    ).fetchone()["cnt"]

    # Platform stats
    platform_stats = conn.execute(
        """SELECT platform, COUNT(*) as total,
                  SUM(CASE WHEN status='published' THEN 1 ELSE 0 END) as published
           FROM posts GROUP BY platform"""
    ).fetchall()

    # Recent activity
    recent = conn.execute(
        "SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT 8"
    ).fetchall()

    # Total stats
    total_posts = conn.execute("SELECT COUNT(*) as c FROM posts").fetchone()["c"]
    total_topics = conn.execute("SELECT COUNT(*) as c FROM topics").fetchone()["c"]
    published = conn.execute(
        "SELECT COUNT(*) as c FROM posts WHERE status='published'"
    ).fetchone()["c"]
    avg_engagement = conn.execute(
        "SELECT COALESCE(AVG(engagement_score), 0) as avg FROM posts WHERE status='published'"
    ).fetchone()["avg"]

    conn.close()

    return render_template(
        "index.html",
        upcoming=upcoming,
        pending_topics=pending_topics,
        platform_stats=platform_stats,
        recent=recent,
        total_posts=total_posts,
        total_topics=total_topics,
        published=published,
        avg_engagement=round(avg_engagement, 1),
        now=now,
    )


@app.route("/topics", methods=["GET", "POST"])
def topics() -> str:
    """Topics management page."""
    conn = get_db()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        platform = request.form.get("platform", "all")
        tags = request.form.get("tags", "").strip()

        if title:
            conn.execute(
                """INSERT INTO topics (title, description, platform, tags)
                   VALUES (?, ?, ?, ?)""",
                (title, description, platform, tags),
            )
            conn.commit()
            log_activity("topic_added", title)

    all_topics = conn.execute(
        "SELECT * FROM topics ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    return render_template("topics.html", topics=all_topics)


@app.route("/topics/<int:topic_id>/status", methods=["POST"])
def update_topic_status(topic_id: int) -> str:
    """Update topic status."""
    status = request.form.get("status", "pending")
    conn = get_db()
    conn.execute(
        "UPDATE topics SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, topic_id),
    )
    conn.commit()
    log_activity("topic_status_updated", f"Topic {topic_id} -> {status}")
    conn.close()
    return redirect(url_for("topics"))


@app.route("/topics/<int:topic_id>/delete", methods=["POST"])
def delete_topic(topic_id: int) -> str:
    """Delete a topic."""
    conn = get_db()
    topic = conn.execute("SELECT title FROM topics WHERE id = ?", (topic_id,)).fetchone()
    if topic:
        conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
        conn.commit()
        log_activity("topic_deleted", topic["title"])
    conn.close()
    return redirect(url_for("topics"))


@app.route("/posts")
def posts() -> str:
    """Content calendar view."""
    conn = get_db()
    now = datetime.now()

    # Get month/year from query params
    year = request.args.get("year", now.year, type=int)
    month = request.args.get("month", now.month, type=int)

    # Build calendar
    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)

    # Get posts for this month
    month_posts = conn.execute(
        """SELECT p.*, t.title as topic_title
           FROM posts p LEFT JOIN topics t ON p.topic_id = t.id
           WHERE p.scheduled_at >= ? AND p.scheduled_at <= ?
           ORDER BY p.scheduled_at""",
        (first_day.isoformat(), last_day.isoformat()),
    ).fetchall()

    # Group by day
    posts_by_day: dict[int, list[sqlite3.Row]] = {}
    for post in month_posts:
        if post["scheduled_at"]:
            day = datetime.fromisoformat(post["scheduled_at"]).day
            posts_by_day.setdefault(day, []).append(post)

    # All posts (non-scheduled drafts)
    draft_posts = conn.execute(
        """SELECT p.*, t.title as topic_title
           FROM posts p LEFT JOIN topics t ON p.topic_id = t.id
           WHERE p.status = 'draft'
           ORDER BY p.created_at DESC LIMIT 20"""
    ).fetchall()

    # Calendar navigation
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    conn.close()

    return render_template(
        "posts.html",
        posts_by_day=posts_by_day,
        draft_posts=draft_posts,
        year=year,
        month=month,
        month_name=first_day.strftime("%B %Y"),
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        today=now.day,
        now=now,
    )


@app.route("/analytics")
def analytics() -> str:
    """Analytics page."""
    conn = get_db()

    # Posts per platform
    platform_data = conn.execute(
        """SELECT platform, COUNT(*) as total,
                  SUM(CASE WHEN status='published' THEN 1 ELSE 0 END) as published,
                  SUM(engagement_score) as total_engagement
           FROM posts GROUP BY platform"""
    ).fetchall()

    # Posts per day (last 30 days)
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    daily_posts = conn.execute(
        """SELECT DATE(scheduled_at) as day, COUNT(*) as cnt
           FROM posts WHERE scheduled_at >= ?
           GROUP BY DATE(scheduled_at) ORDER BY day""",
        (thirty_days_ago,),
    ).fetchall()

    # Topic conversion rate
    total_topics = conn.execute("SELECT COUNT(*) as c FROM topics").fetchone()["c"]
    topics_with_posts = conn.execute(
        "SELECT COUNT(DISTINCT topic_id) as c FROM posts WHERE topic_id IS NOT NULL"
    ).fetchone()["c"]

    # Top engaged posts
    top_posts = conn.execute(
        """SELECT p.*, t.title as topic_title
           FROM posts p LEFT JOIN topics t ON p.topic_id = t.id
           WHERE p.status = 'published'
           ORDER BY p.engagement_score DESC LIMIT 5"""
    ).fetchall()

    conn.close()

    return render_template(
        "analytics.html",
        platform_data=platform_data,
        daily_posts=daily_posts,
        total_topics=total_topics,
        topics_with_posts=topics_with_posts,
        top_posts=top_posts,
    )


@app.route("/settings", methods=["GET", "POST"])
def settings() -> str:
    """Settings page."""
    conn = get_db()

    if request.method == "POST":
        log_activity("settings_updated", "Dashboard settings updated")
        # In a real app, save settings to a config table
        return redirect(url_for("settings"))

    conn.close()
    return render_template("settings.html")


# --- API Endpoints (for bot/scheduler) ---


@app.route("/api/topics", methods=["GET"])
def api_topics() -> jsonify:
    """API: Get all topics."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM topics ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/topics", methods=["POST"])
def api_add_topic() -> tuple[jsonify, int]:
    """API: Add a topic."""
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"error": "title required"}), 400

    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO topics (title, description, platform, tags)
           VALUES (?, ?, ?, ?)""",
        (
            data["title"],
            data.get("description", ""),
            data.get("platform", "all"),
            data.get("tags", ""),
        ),
    )
    conn.commit()
    topic_id = cursor.lastrowid
    log_activity("topic_added_api", data["title"])
    conn.close()
    return jsonify({"id": topic_id, "message": "Topic added"}), 201


@app.route("/api/posts", methods=["GET"])
def api_posts() -> jsonify:
    """API: Get all posts."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM posts ORDER BY scheduled_at DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/posts", methods=["POST"])
def api_add_post() -> tuple[jsonify, int]:
    """API: Add a post."""
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"error": "title required"}), 400

    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO posts (topic_id, title, content, platform, status, scheduled_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            data.get("topic_id"),
            data["title"],
            data.get("content", ""),
            data.get("platform", "all"),
            data.get("status", "draft"),
            data.get("scheduled_at"),
        ),
    )
    conn.commit()
    post_id = cursor.lastrowid
    log_activity("post_added_api", data["title"])
    conn.close()
    return jsonify({"id": post_id, "message": "Post added"}), 201


@app.route("/api/stats", methods=["GET"])
def api_stats() -> jsonify:
    """API: Get dashboard stats."""
    conn = get_db()
    stats = {
        "total_topics": conn.execute("SELECT COUNT(*) as c FROM topics").fetchone()["c"],
        "total_posts": conn.execute("SELECT COUNT(*) as c FROM posts").fetchone()["c"],
        "pending_topics": conn.execute(
            "SELECT COUNT(*) as c FROM topics WHERE status='pending'"
        ).fetchone()["c"],
        "published_posts": conn.execute(
            "SELECT COUNT(*) as c FROM posts WHERE status='published'"
        ).fetchone()["c"],
        "scheduled_posts": conn.execute(
            "SELECT COUNT(*) as c FROM posts WHERE status='scheduled'"
        ).fetchone()["c"],
    }
    conn.close()
    return jsonify(stats)


def create_app() -> Flask:
    """Create and configure the Flask app."""
    app.config["SECRET_KEY"] = "content-agent-dashboard"
    return app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
