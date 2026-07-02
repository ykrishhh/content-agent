"""Telegram bot for AI Content Agent using raw HTTP API."""

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "content.db"
API_BASE = "https://api.telegram.org/bot{}"


class TelegramBot:
    """Telegram bot using raw HTTP requests (no python-telegram-bot dependency)."""

    def __init__(self, token: str, chat_id: str = "") -> None:
        self.token = token
        self.chat_id = chat_id
        self.api_url = API_BASE.format(token)
        self._offset = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the bot polling in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("Telegram bot started polling")

    def stop(self) -> None:
        """Stop the bot."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Telegram bot stopped")

    def _poll_loop(self) -> None:
        """Long-polling loop."""
        while self._running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._handle_update(update)
            except requests.RequestException as e:
                logger.warning("Poll error: %s", e)
                time.sleep(5)
            except Exception as e:
                logger.error("Poll loop error: %s", e)
                time.sleep(5)

    def _get_updates(self) -> list[dict[str, Any]]:
        """Fetch updates from Telegram."""
        resp = requests.get(
            f"{self.api_url}/getUpdates",
            params={"offset": self._offset, "timeout": 30},
            timeout=35,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            return data.get("result", [])
        return []

    def _handle_update(self, update: dict[str, Any]) -> None:
        """Handle a single Telegram update."""
        self._offset = update["update_id"] + 1

        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        text = message.get("text", "")
        chat_id = message["chat"]["id"]
        user = message.get("from", {})
        username = user.get("username", user.get("first_name", "unknown"))

        if not text.startswith("/"):
            return

        parts = text.split(maxsplit=1)
        command = parts[0].lower().split("@")[0]  # Remove bot mention
        args = parts[1] if len(parts) > 1 else ""

        logger.info("Command from %s: %s %s", username, command, args)

        handlers = {
            "/start": self._cmd_start,
            "/add_topic": self._cmd_add_topic,
            "/list_topics": self._cmd_list_topics,
            "/generate": self._cmd_generate,
            "/status": self._cmd_status,
            "/schedule": self._cmd_schedule,
            "/help": self._cmd_help,
        }

        handler = handlers.get(command)
        if handler:
            try:
                handler(chat_id, args, username)
            except Exception as e:
                logger.error("Command error: %s", e)
                self._send_message(chat_id, f"Error: {e}")
        else:
            self._send_message(chat_id, f"Unknown command: {command}\nType /help for available commands.")

    def _send_message(self, chat_id: int, text: str, parse_mode: str = "") -> None:
        """Send a message via Telegram API."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            resp = requests.post(f"{self.api_url}/sendMessage", json=payload, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error("Send message failed: %s", e)

    # --- Command Handlers ---

    def _cmd_start(self, chat_id: int, args: str, username: str) -> None:
        """Handle /start command."""
        text = (
            f"Welcome to AI Content Agent!\n\n"
            f"Commands:\n"
            f"/add_topic <title> - Add a new content topic\n"
            f"/list_topics - View all topics\n"
            f"/generate <topic_id> - Generate content for a topic\n"
            f"/status - View bot status\n"
            f"/schedule - View scheduled posts\n"
            f"/help - Show this help message"
        )
        self._send_message(chat_id, text)

    def _cmd_add_topic(self, chat_id: int, args: str, username: str) -> None:
        """Handle /add_topic command."""
        if not args.strip():
            self._send_message(chat_id, "Usage: /add_topic <topic title>")
            return

        title = args.strip()
        conn = self._get_db()
        try:
            cursor = conn.execute(
                "INSERT INTO topics (title, description, status) VALUES (?, ?, 'pending')",
                (title, f"Added by @{username} via Telegram"),
            )
            conn.commit()
            topic_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO activity_log (action, details) VALUES (?, ?)",
                ("topic_added_telegram", f"{title} (by @{username})"),
            )
            conn.commit()
            self._send_message(chat_id, f"Topic added!\n\nID: #{topic_id}\nTitle: {title}\nStatus: pending")
        finally:
            conn.close()

    def _cmd_list_topics(self, chat_id: int, args: str, username: str) -> None:
        """Handle /list_topics command."""
        conn = self._get_db()
        try:
            rows = conn.execute(
                "SELECT id, title, status, platform FROM topics ORDER BY created_at DESC LIMIT 20"
            ).fetchall()

            if not rows:
                self._send_message(chat_id, "No topics yet. Use /add_topic to create one.")
                return

            lines = ["Topics:\n"]
            status_icons = {
                "pending": "⏳",
                "in_progress": "🔄",
                "completed": "✅",
                "archived": "📦",
            }
            for row in rows:
                icon = status_icons.get(row["status"], "❓")
                lines.append(f"{icon} #{row['id']} — {row['title']}")
                lines.append(f"   Status: {row['status']} | Platform: {row['platform']}")

            self._send_message(chat_id, "\n".join(lines))
        finally:
            conn.close()

    def _cmd_generate(self, chat_id: int, args: str, username: str) -> None:
        """Handle /generate command — generate content for a topic."""
        if not args.strip():
            self._send_message(chat_id, "Usage: /generate <topic_id>")
            return

        try:
            topic_id = int(args.strip())
        except ValueError:
            self._send_message(chat_id, "Invalid topic ID. Use a number.")
            return

        conn = self._get_db()
        try:
            topic = conn.execute(
                "SELECT * FROM topics WHERE id = ?", (topic_id,)
            ).fetchone()

            if not topic:
                self._send_message(chat_id, f"Topic #{topic_id} not found.")
                return

            # Create a draft post
            title = f"Post: {topic['title']}"
            content = (
                f"Draft content for topic: {topic['title']}\n\n"
                f"This is a placeholder. Connect an AI provider to generate real content.\n"
                f"Set AI_API_KEY and AI_PROVIDER in your .env file."
            )

            cursor = conn.execute(
                """INSERT INTO posts (topic_id, title, content, platform, status)
                   VALUES (?, ?, ?, ?, 'draft')""",
                (topic_id, title, content, topic["platform"]),
            )
            conn.commit()
            post_id = cursor.lastrowid

            conn.execute(
                "UPDATE topics SET status = 'in_progress', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (topic_id,),
            )
            conn.commit()

            conn.execute(
                "INSERT INTO activity_log (action, details) VALUES (?, ?)",
                ("content_generated", f"Post #{post_id} for topic #{topic_id}"),
            )
            conn.commit()

            self._send_message(
                chat_id,
                f"Content generated!\n\n"
                f"Post ID: #{post_id}\n"
                f"Topic: {topic['title']}\n"
                f"Status: draft\n"
                f"Platform: {topic['platform']}\n\n"
                f"Edit via the dashboard at http://localhost:5000/posts",
            )
        finally:
            conn.close()

    def _cmd_status(self, chat_id: int, args: str, username: str) -> None:
        """Handle /status command."""
        conn = self._get_db()
        try:
            stats = {
                "topics": conn.execute("SELECT COUNT(*) as c FROM topics").fetchone()["c"],
                "posts": conn.execute("SELECT COUNT(*) as c FROM posts").fetchone()["c"],
                "pending": conn.execute(
                    "SELECT COUNT(*) as c FROM topics WHERE status='pending'"
                ).fetchone()["c"],
                "drafts": conn.execute(
                    "SELECT COUNT(*) as c FROM posts WHERE status='draft'"
                ).fetchone()["c"],
                "published": conn.execute(
                    "SELECT COUNT(*) as c FROM posts WHERE status='published'"
                ).fetchone()["c"],
            }

            # Next scheduled post
            next_post = conn.execute(
                """SELECT title, scheduled_at FROM posts
                   WHERE status='scheduled' AND scheduled_at >= datetime('now')
                   ORDER BY scheduled_at ASC LIMIT 1"""
            ).fetchone()

            text = (
                f"Bot Status\n\n"
                f"Topics: {stats['topics']} ({stats['pending']} pending)\n"
                f"Posts: {stats['posts']} ({stats['drafts']} drafts, {stats['published']} published)\n"
            )

            if next_post:
                text += f"\nNext post: {next_post['title']}\nScheduled: {next_post['scheduled_at']}"
            else:
                text += "\nNo posts scheduled."

            self._send_message(chat_id, text)
        finally:
            conn.close()

    def _cmd_schedule(self, chat_id: int, args: str, username: str) -> None:
        """Handle /schedule command — view scheduled posts."""
        conn = self._get_db()
        try:
            rows = conn.execute(
                """SELECT p.id, p.title, p.platform, p.scheduled_at
                   FROM posts p
                   WHERE p.status = 'scheduled' AND p.scheduled_at >= datetime('now')
                   ORDER BY p.scheduled_at ASC LIMIT 10"""
            ).fetchall()

            if not rows:
                self._send_message(chat_id, "No posts scheduled.")
                return

            lines = ["Scheduled Posts:\n"]
            for row in rows:
                dt = row["scheduled_at"][:16].replace("T", " ")
                lines.append(f"#{row['id']} — {row['title']}")
                lines.append(f"   {row['platform']} | {dt}")

            self._send_message(chat_id, "\n".join(lines))
        finally:
            conn.close()

    def _cmd_help(self, chat_id: int, args: str, username: str) -> None:
        """Handle /help command."""
        text = (
            "AI Content Agent — Commands\n\n"
            "/start — Welcome message\n"
            "/add_topic <title> — Add a content topic\n"
            "/list_topics — List all topics\n"
            "/generate <topic_id> — Generate content for a topic\n"
            "/status — View bot and content status\n"
            "/schedule — View upcoming scheduled posts\n"
            "/help — Show this help\n\n"
            "Web Dashboard: http://localhost:5000"
        )
        self._send_message(chat_id, text)

    def send_notification(self, text: str) -> None:
        """Send a notification to the configured chat."""
        if not self.chat_id:
            return
        try:
            self._send_message(int(self.chat_id), text)
        except (ValueError, Exception) as e:
            logger.error("Notification failed: %s", e)

    @staticmethod
    def _get_db() -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn
