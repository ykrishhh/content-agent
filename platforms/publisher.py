"""Multi-platform publisher orchestrator."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Shared post model
# ------------------------------------------------------------------

class Platform(str, Enum):
    GITHUB = "github"
    TELEGRAM = "telegram"
    EMAIL = "email"
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"


@dataclass
class Post:
    """Platform-agnostic content post.

    Each platform client's ``create_post`` / ``send_message`` method
    is called with the appropriate subset of these fields.
    """

    title: str
    body: str
    html_body: str = ""
    image_url: str = ""
    tags: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PublishResult:
    """Outcome of publishing to a single platform."""

    platform: Platform
    ok: bool
    post_id: str = ""
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------
# Publisher
# ------------------------------------------------------------------

@dataclass
class Publisher:
    """Publish a :class:`Post` to one or more platforms.

    Pass whichever client instances you have configured::

        publisher = Publisher(
            github=github_client,
            telegram=telegram_client,
        )
        results = publisher.publish(post, platforms=[Platform.GITHUB, Platform.TELEGRAM])

    Platforms that were *not* provided are silently skipped.
    """

    github: Any = None
    telegram: Any = None
    email: Any = None
    linkedin: Any = None
    instagram: Any = None

    # ------------------------------------------------------------------
    # Dispatch helpers
    # ------------------------------------------------------------------

    def _publish_github(self, post: Post) -> PublishResult:
        if self.github is None:
            return PublishResult(platform=Platform.GITHUB, ok=False, error="client not configured")
        try:
            data = self.github.create_post(post.title, post.body)
            ok = data.get("ok", False)
            return PublishResult(
                platform=Platform.GITHUB,
                ok=ok,
                post_id=data.get("tag", ""),
                details=data,
            )
        except Exception as exc:
            logger.error("GitHub publish failed: %s", exc)
            return PublishResult(platform=Platform.GITHUB, ok=False, error=str(exc))

    def _publish_telegram(self, post: Post) -> PublishResult:
        if self.telegram is None:
            return PublishResult(platform=Platform.TELEGRAM, ok=False, error="client not configured")
        try:
            text = f"<b>{post.title}</b>\n\n{post.body}"
            data = self.telegram.send_message(text)
            ok = data.get("ok", False)
            msg_id = str(data.get("result", {}).get("message_id", ""))
            return PublishResult(
                platform=Platform.TELEGRAM,
                ok=ok,
                post_id=msg_id,
                details=data,
            )
        except Exception as exc:
            logger.error("Telegram publish failed: %s", exc)
            return PublishResult(platform=Platform.TELEGRAM, ok=False, error=str(exc))

    def _publish_email(self, post: Post) -> PublishResult:
        if self.email is None:
            return PublishResult(platform=Platform.EMAIL, ok=False, error="client not configured")
        try:
            html = post.html_body or f"<h1>{post.title}</h1><div>{post.body}</div>"
            recipients = post.metadata.get("recipients", [])
            if not recipients:
                return PublishResult(platform=Platform.EMAIL, ok=False, error="no recipients in metadata")
            data = self.email.send_bulk(recipients, post.title, html)
            return PublishResult(
                platform=Platform.EMAIL,
                ok=data.get("ok", False),
                details=data,
            )
        except Exception as exc:
            logger.error("Email publish failed: %s", exc)
            return PublishResult(platform=Platform.EMAIL, ok=False, error=str(exc))

    def _publish_linkedin(self, post: Post) -> PublishResult:
        if self.linkedin is None:
            return PublishResult(platform=Platform.LINKEDIN, ok=False, error="client not configured")
        try:
            text = f"{post.title}\n\n{post.body}"
            if post.hashtags:
                text += "\n\n" + " ".join(f"#{t.lstrip('#')}" for t in post.hashtags)
            data = self.linkedin.create_post(text)
            ok = "id" in data or data.get("status") == 201
            return PublishResult(
                platform=Platform.LINKEDIN,
                ok=ok,
                post_id=data.get("id", ""),
                details=data,
            )
        except Exception as exc:
            logger.error("LinkedIn publish failed: %s", exc)
            return PublishResult(platform=Platform.LINKEDIN, ok=False, error=str(exc))

    def _publish_instagram(self, post: Post) -> PublishResult:
        if self.instagram is None:
            return PublishResult(platform=Platform.INSTAGRAM, ok=False, error="client not configured")
        if not post.image_url:
            return PublishResult(platform=Platform.INSTAGRAM, ok=False, error="image_url is required for Instagram")
        try:
            caption = self.instagram.generate_caption(
                f"{post.title}\n\n{post.body}",
                hashtags=post.hashtags,
            )
            data = self.instagram.create_post(post.image_url, caption)
            ok = data.get("ok", False)
            return PublishResult(
                platform=Platform.INSTAGRAM,
                ok=ok,
                post_id=data.get("media_id", ""),
                details=data,
            )
        except Exception as exc:
            logger.error("Instagram publish failed: %s", exc)
            return PublishResult(platform=Platform.INSTAGRAM, ok=False, error=str(exc))

    _DISPATCH = {
        Platform.GITHUB: "_publish_github",
        Platform.TELEGRAM: "_publish_telegram",
        Platform.EMAIL: "_publish_email",
        Platform.LINKEDIN: "_publish_linkedin",
        Platform.INSTAGRAM: "_publish_instagram",
    }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish(
        self,
        post: Post,
        *,
        platforms: list[Platform] | None = None,
    ) -> dict[Platform, PublishResult]:
        """Publish *post* to the requested platforms.

        If *platforms* is ``None``, every configured (non-None) client
        is used.

        Returns a dict mapping each platform to its :class:`PublishResult`.
        """
        if platforms is None:
            platforms = [p for p in Platform if getattr(self, p.value) is not None]

        results: dict[Platform, PublishResult] = {}
        for p in platforms:
            method = self._DISPATCH.get(p)
            if method is None:
                results[p] = PublishResult(platform=p, ok=False, error="unknown platform")
                continue
            logger.info("Publishing to %s …", p.value)
            results[p] = getattr(self, method)(post)

        # Summary
        succeeded = sum(1 for r in results.values() if r.ok)
        logger.info(
            "Publish complete: %d/%d succeeded",
            succeeded,
            len(results),
        )
        return results

    def summary(self, results: dict[Platform, PublishResult]) -> str:
        """Return a human-readable one-line summary of publish results."""
        parts = []
        for p, r in results.items():
            status = "ok" if r.ok else f"FAIL: {r.error}"
            parts.append(f"{p.value}={status}")
        return " | ".join(parts)
