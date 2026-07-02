"""Instagram Graph API client (requires a Facebook Business/Creator account)."""

from __future__ import annotations

import logging
import random
import string
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

_GRAPH = "https://graph.facebook.com/v19.0"


@dataclass
class InstagramClient:
    """Client for the Instagram Graph API.

    Requirements:
    * An Instagram **Business** or **Creator** account linked to a
      Facebook Page.
    * A Facebook App with the ``instagram_basic``,
      ``instagram_content_publish``, and ``pages_read_engagement``
      permissions approved.
    * A short-lived or long-lived Facebook User Access Token with
      the above scopes.

    Parameters
    ----------
    access_token:
        A valid Facebook/Instagram Graph API access token.
    ig_user_id:
        The Instagram Business/Creator Account ID (numeric).
    """

    access_token: str = ""
    ig_user_id: str = ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload.setdefault("access_token", self.access_token)
        try:
            resp = requests.post(url, data=payload, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("Instagram POST failed: %s", exc)
            return {"error": str(exc)}

    def _get(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        params.setdefault("access_token", self.access_token)
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("Instagram GET failed: %s", exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Caption generation
    # ------------------------------------------------------------------

    def generate_caption(
        self,
        text: str,
        *,
        hashtags: list[str] | None = None,
        max_length: int = 2200,
    ) -> str:
        """Build an Instagram caption with optional hashtags.

        Instagram allows up to 2 200 characters for a caption.
        """
        parts: list[str] = [text.strip()]
        if hashtags:
            tag_str = " ".join(f"#{t.lstrip('#')}" for t in hashtags)
            # Reserve space for hashtags
            remaining = max_length - len(parts[0]) - 2  # 2 for newline
            if len(tag_str) <= remaining:
                parts.append(tag_str)
            else:
                # Truncate hashtags to fit
                truncated = tag_str[:remaining].rsplit(" ", 1)[0]
                parts.append(truncated)
        caption = "\n\n".join(parts)
        logger.debug("Generated caption: %d chars", len(caption))
        return caption

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def create_post(
        self,
        image_url: str,
        caption: str,
        *,
        user_tags: list[dict[str, str]] | None = None,
        location_id: str = "",
    ) -> dict[str, Any]:
        """Publish a photo post to Instagram.

        Parameters
        ----------
        image_url:
            A publicly accessible URL to the image (must be ≥ 320 px wide).
        caption:
            The post caption (max 2 200 chars).
        user_tags:
            Optional list of ``{"username": "...", "x": 0.5, "y": 0.5}``
            dicts for tagging users (coordinates are 0.0–1.0).
        location_id:
            Optional Facebook Page location ID.
        """
        # Step 1 — create a media container
        container_payload: dict[str, Any] = {
            "image_url": image_url,
            "caption": caption,
        }
        if user_tags:
            container_payload["user_tags"] = {"tags": user_tags}
        if location_id:
            container_payload["location_id"] = location_id

        container = self._post(
            f"{_GRAPH}/{self.ig_user_id}/media",
            container_payload,
        )
        container_id = container.get("id")
        if not container_id:
            logger.error("Failed to create media container: %s", container)
            return {"ok": False, **container}

        # Step 2 — publish
        publish = self._post(
            f"{_GRAPH}/{self.ig_user_id}/media_publish",
            {"creation_id": container_id},
        )
        media_id = publish.get("id")
        if media_id:
            logger.info("Instagram post published: %s", media_id)
            return {"ok": True, "media_id": media_id}
        logger.error("Publish step failed: %s", publish)
        return {"ok": False, **publish}

    # ------------------------------------------------------------------
    # Scheduling (via Facebook Content Publishing API)
    # ------------------------------------------------------------------

    def schedule_post(
        self,
        image_url: str,
        caption: str,
        scheduled_timestamp: int,
    ) -> dict[str, Any]:
        """Schedule a photo post.

        Parameters
        ----------
        scheduled_timestamp:
            Unix epoch in **seconds** when the post should go live.
            Must be at least 1 hour in the future.

        Note: the container is created with ``published=false`` so it
        sits in a *pending* state until the scheduled time.
        """
        container = self._post(
            f"{_GRAPH}/{self.ig_user_id}/media",
            {
                "image_url": image_url,
                "caption": caption,
                "published": "false",
                "scheduled_publish_time": str(scheduled_timestamp),
            },
        )
        container_id = container.get("id")
        if not container_id:
            logger.error("Failed to create scheduled container: %s", container)
            return {"ok": False, **container}

        logger.info("Instagram post scheduled (container=%s, time=%s)", container_id, scheduled_timestamp)
        return {"ok": True, "container_id": container_id, "scheduled_timestamp": scheduled_timestamp}

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def get_profile(self) -> dict[str, Any]:
        """Return basic profile info."""
        return self._get(f"{_GRAPH}/{self.ig_user_id}", {
            "fields": "id,username,name,biography,followers_count,media_count",
        })

    def get_recent_media(self, limit: int = 25) -> list[dict[str, Any]]:
        """Fetch recent media objects."""
        data = self._get(f"{_GRAPH}/{self.ig_user_id}/media", {
            "fields": "id,caption,media_type,media_url,timestamp,permalink",
            "limit": str(limit),
        })
        return data.get("data", [])
