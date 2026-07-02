"""
Autonomous AI Content Agent - Core Package

A self-contained content generation and scheduling system
designed to run on Termux with minimal dependencies.
"""

from .models import Topic, Post, Platform, ContentStatus, ScheduleSlot
from .db import DatabaseManager
from .topic_researcher import TopicResearcher
from .content_generator import ContentGenerator
from .seo_optimizer import SEOOptimizer
from .content_pipeline import ContentPipeline
from .agent import ContentAgent

__all__ = [
    "Topic",
    "Post",
    "Platform",
    "ContentStatus",
    "ScheduleSlot",
    "DatabaseManager",
    "TopicResearcher",
    "ContentGenerator",
    "SEOOptimizer",
    "ContentPipeline",
    "ContentAgent",
]

__version__ = "0.1.0"
