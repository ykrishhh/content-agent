"""Telegram Bot API client."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

_BASE = "https://api.telegram.org"


@dataclass
class TelegramClient:
    """Thin wrapper around the Telegram Bot API.

    Parameters
    ----------
    token:
        The bot token from BotFather.
    chat_id:
        Default channel / group / user chat id.
    """

    token: str
    chat_id: str = ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _url(self, method: str) -> str:
        return f"{_BASE}/bot{self.token}/{method}"

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to the Telegram API and return the JSON body."""
        url = self._url(method)
        logger.debug("POST %s", url)
        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error("Telegram API error: %s", data.get("description"))
            return data
        except requests.RequestException as exc:
            logger.error("Telegram request failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_message(
        self,
        text: str,
        *,
        chat_id: str = "",
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = False,
    ) -> dict[str, Any]:
        """Send a text message to a chat."""
        target = chat_id or self.chat_id
        if not target:
            raise ValueError("chat_id must be provided or set on the client")
        return self._post("sendMessage", {
            "chat_id": target,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        })

    def send_post_preview(
        self,
        text: str,
        *,
        chat_id: str = "",
        parse_mode: str = "HTML",
    ) -> dict[str, Any]:
        """Send a message *without* link preview (useful for draft previews)."""
        return self.send_message(
            text,
            chat_id=chat_id,
            parse_mode=parse_mode,
            disable_web_page_preview=True,
        )

    def create_channel_post(
        self,
        text: str,
        *,
        channel_id: str = "",
        parse_mode: str = "HTML",
    ) -> dict[str, Any]:
        """Post a message to a Telegram channel.

        The bot must be an admin of the channel.
        """
        target = channel_id or self.chat_id
        if not target:
            raise ValueError("channel_id must be provided or set on the client")
        return self._post("sendMessage", {
            "chat_id": target,
            "text": text,
            "parse_mode": parse_mode,
        })

    def broadcast(
        self,
        text: str,
        chat_ids: list[str],
        *,
        parse_mode: str = "HTML",
    ) -> dict[str, Any]:
        """Send the same message to multiple chats.

        Returns a summary dict with ``sent`` and ``failed`` counts.
        """
        sent = 0
        failed = 0
        for cid in chat_ids:
            result = self.send_message(text, chat_id=cid, parse_mode=parse_mode)
            if result.get("ok"):
                sent += 1
            else:
                failed += 1
        summary = {"sent": sent, "failed": failed, "total": len(chat_ids)}
        logger.info("Broadcast complete: %s", summary)
        return summary

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def get_me(self) -> dict[str, Any]:
        """Return basic info about the bot."""
        return self._post("getMe", {})

    def set_webhook(self, url: str) -> dict[str, Any]:
        """Register a webhook URL."""
        return self._post("setWebhook", {"url": url})
