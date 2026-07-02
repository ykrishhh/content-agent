#!/usr/bin/env python3
"""AI Content Agent — Entry point.

Starts the dashboard, Telegram bot, and scheduler concurrently.
Use CLI args to select which components to run.

Usage:
    python main.py                  # Start all components
    python main.py --dashboard      # Dashboard only
    python main.py --bot            # Telegram bot only
    python main.py --scheduler      # Scheduler only
    python main.py --dashboard --bot  # Dashboard + bot
"""

import argparse
import logging
import signal
import sys
import threading
from typing import NoReturn

from config.settings import Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def start_dashboard(settings: Settings) -> None:
    """Start the Flask dashboard in a thread."""
    from dashboard.app import app

    def _run() -> None:
        app.run(
            host=settings.dashboard_host,
            port=settings.dashboard_port,
            debug=False,
            use_reloader=False,
        )

    thread = threading.Thread(target=_run, daemon=True, name="dashboard")
    thread.start()
    logger.info(
        "Dashboard running at http://%s:%d",
        settings.dashboard_host,
        settings.dashboard_port,
    )


def start_telegram_bot(settings: Settings) -> None:
    """Start the Telegram bot."""
    from telegram_bot.bot import TelegramBot

    if not settings.has_telegram:
        logger.warning("Telegram bot token not set. Bot will not start.")
        return

    bot = TelegramBot(
        token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )
    bot.start()
    logger.info("Telegram bot started")


def start_scheduler(settings: Settings) -> None:
    """Start the content scheduler."""
    from scheduler.cron import Scheduler

    def on_notify(message: str) -> None:
        logger.info("Notification: %s", message)

    scheduler = Scheduler(
        check_interval=settings.check_interval_minutes * 60,
        on_notify=on_notify,
    )
    scheduler.start()
    logger.info(
        "Scheduler started (check every %d minutes)",
        settings.check_interval_minutes,
    )


def wait_for_shutdown() -> NoReturn:
    """Block until SIGINT/SIGTERM, then exit."""
    shutdown_event = threading.Event()

    def _signal_handler(sig: int, frame: object) -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    logger.info("Press Ctrl+C to stop")
    shutdown_event.wait()
    logger.info("Shutting down...")
    sys.exit(0)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="AI Content Agent — Dashboard, Telegram Bot, and Scheduler",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Start the web dashboard",
    )
    parser.add_argument(
        "--bot",
        action="store_true",
        help="Start the Telegram bot",
    )
    parser.add_argument(
        "--scheduler",
        action="store_true",
        help="Start the content scheduler",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=True,
        help="Start all components (default)",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = parse_args()
    settings = Settings()

    # Determine which components to start
    start_all = args.all or (not args.dashboard and not args.bot and not args.scheduler)

    print("=" * 50)
    print("  AI Content Agent")
    print("=" * 50)
    print()
    print(f"  Database: {settings.database_path}")
    print(f"  AI Provider: {settings.ai_provider}")
    print(f"  Telegram: {'configured' if settings.has_telegram else 'not configured'}")
    print()

    if start_all or args.dashboard:
        start_dashboard(settings)

    if start_all or args.bot:
        start_telegram_bot(settings)

    if start_all or args.scheduler:
        start_scheduler(settings)

    wait_for_shutdown()


if __name__ == "__main__":
    main()
