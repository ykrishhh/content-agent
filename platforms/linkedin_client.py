"""LinkedIn API client (requires OAuth 2.0 — placeholder structure)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

_API = "https://api.linkedin.com/v2"
_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"


@dataclass
class LinkedInClient:
    """Client for the LinkedIn Marketing / Posts API.

    LinkedIn requires OAuth 2.0 with a registered app.  Set
    ``access_token`` after completing the OAuth flow::

        client = LinkedInClient(client_id="...", client_secret="...")
        # redirect user to client.get_auth_url(redirect_uri, state="...")
        # exchange code for token via client.exchange_code(code, redirect_uri)

    Required OAuth scopes: ``w_member_social``, ``r_liteprofile``,
    ``r_emailaddress``.
    """

    client_id: str = ""
    client_secret: str = ""
    access_token: str = ""

    # ------------------------------------------------------------------
    # OAuth helpers
    # ------------------------------------------------------------------

    def get_auth_url(self, redirect_uri: str, *, state: str = "random") -> str:
        """Return the URL the user should visit to authorize the app."""
        params = (
            f"response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&scope=w_member_social%20r_liteprofile%20r_emailaddress"
            f"&state={state}"
        )
        return f"{_AUTH_URL}?{params}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange an authorization code for an access token."""
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        try:
            resp = requests.post(_TOKEN_URL, data=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data.get("access_token", "")
            logger.info("LinkedIn token obtained (expires_in=%s)", data.get("expires_in"))
            return data
        except requests.RequestException as exc:
            logger.error("Token exchange failed: %s", exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            logger.debug("LinkedIn POST %s -> %s", url, data)
            return data
        except requests.RequestException as exc:
            logger.error("LinkedIn request failed: %s", exc)
            return {"error": str(exc)}

    def _get(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("LinkedIn GET failed: %s", exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Posts
    # ------------------------------------------------------------------

    def create_post(
        self,
        text: str,
        *,
        visibility: str = "PUBLIC",
    ) -> dict[str, Any]:
        """Create a text post on the authenticated member's feed.

        LinkedIn uses UGC (User Generated Content) API v2.
        """
        payload = {
            "author": "urn:li:person:me",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                },
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility,
            },
        }
        return self._post(f"{_API}/ugcPosts", payload)

    def schedule_post(
        self,
        text: str,
        scheduled_time: datetime,
        *,
        visibility: str = "PUBLIC",
    ) -> dict[str, Any]:
        """Schedule a post for a future time.

        ``scheduled_time`` must be in UTC and at least 1 hour in the future.
        LinkedIn's API accepts a ``timestamp`` (epoch seconds) in the
        ``lifecycleState`` field.
        """
        now = datetime.now(timezone.utc)
        if scheduled_time <= now:
            return {"error": "scheduled_time must be in the future"}
        if (scheduled_time - now).total_seconds() < 3600:
            logger.warning("LinkedIn requires scheduling at least 1 hour ahead")

        payload = {
            "author": "urn:li:person:me",
            "lifecycleState": "SCHEDULED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                },
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility,
            },
            "scheduledTime": int(scheduled_time.timestamp() * 1000),
        }
        return self._post(f"{_API}/ugcPosts", payload)

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def get_analytics(self, post_urn: str = "") -> dict[str, Any]:
        """Fetch basic analytics for a post.

        If *post_urn* is empty, a recent-posts summary is returned.
        Requires the ``r_analytics`` or ``rw_analytics`` scope.
        """
        if post_urn:
            url = f"{_API}/organizationalEntityShareStatistics"
            params = {"q": "organizationalEntity", "shares": post_urn}
        else:
            url = f"{_API}/organizationalEntityShareStatistics"
            params = {"q": "organizationalEntity"}
        return self._get(url, params=params)

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    def get_profile(self) -> dict[str, Any]:
        """Fetch the authenticated member's basic profile."""
        return self._get(f"{_API}/me")
