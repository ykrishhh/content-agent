"""Configuration settings for AI Content Agent."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Settings:
    """Application settings loaded from environment or .env file."""

    # Paths
    base_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    database_path: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "content.db")

    # Telegram Bot
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # API Keys
    github_token: str = ""
    email_api_key: str = ""
    linkedin_api_key: str = ""
    instagram_api_key: str = ""

    # AI Provider
    ai_provider: str = "openai"  # openai, anthropic, local
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_base_url: Optional[str] = None

    # Scheduling
    check_interval_minutes: int = 15
    default_post_times: list[str] = field(default_factory=lambda: ["09:00", "12:00", "17:00"])

    # Dashboard
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 5000
    dashboard_secret_key: str = "change-me-in-production"

    # Content
    max_topics_per_day: int = 5
    max_posts_per_day: int = 3
    content_retry_attempts: int = 3

    def __post_init__(self) -> None:
        self._load_env()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_env(self) -> None:
        """Load settings from .env file and environment variables."""
        env_path = self.base_dir / ".env"
        if env_path.exists():
            self._parse_env_file(env_path)

        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", self.telegram_bot_token)
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", self.telegram_chat_id)
        self.github_token = os.getenv("GITHUB_TOKEN", self.github_token)
        self.email_api_key = os.getenv("EMAIL_API_KEY", self.email_api_key)
        self.linkedin_api_key = os.getenv("LINKEDIN_API_KEY", self.linkedin_api_key)
        self.instagram_api_key = os.getenv("INSTAGRAM_API_KEY", self.instagram_api_key)
        self.ai_provider = os.getenv("AI_PROVIDER", self.ai_provider)
        self.ai_api_key = os.getenv("AI_API_KEY", self.ai_api_key)
        self.ai_model = os.getenv("AI_MODEL", self.ai_model)
        self.ai_base_url = os.getenv("AI_BASE_URL", self.ai_base_url)
        self.dashboard_host = os.getenv("DASHBOARD_HOST", self.dashboard_host)
        self.dashboard_port = int(os.getenv("DASHBOARD_PORT", str(self.dashboard_port)))
        self.dashboard_secret_key = os.getenv("DASHBOARD_SECRET_KEY", self.dashboard_secret_key)

    def _parse_env_file(self, path: Path) -> None:
        """Parse a .env file."""
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and not os.getenv(key):
                        os.environ[key] = value

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def has_ai(self) -> bool:
        return bool(self.ai_api_key)
