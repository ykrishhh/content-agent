"""
Content generator — template-based multi-platform output.

Produces blog posts, LinkedIn articles, Instagram captions,
Twitter threads, and email newsletters from a Topic + angle.
No external AI APIs — uses deterministic templates with variable substitution.
"""

from __future__ import annotations

import re
import textwrap
from datetime import datetime
from typing import Optional

from .models import ContentStatus, Platform, Post, Topic


# ---------- templates --------------------------------------------------------

_TEMPLATES: dict[str, str] = {
    Platform.BLOG.value: textwrap.dedent("""\
        # {title}

        > {angle}

        ## Introduction

        {intro}

        ## Key Points

        {key_points}

        ## Practical Tips

        {tips}

        ## Conclusion

        {conclusion}

        ---
        *Tags: {tags}*
        *Reading time: {reading_time} min*
    """),

    Platform.LINKEDIN.value: textwrap.dedent("""\
        {hook}

        {body}

        {tips_linkedin}

        {cta}

        {hashtags}
    """),

    Platform.INSTAGRAM.value: textwrap.dedent("""\
        {caption}

        {hashtags_ig}
    """),

    Platform.TWITTER.value: textwrap.dedent("""\
        {thread}
    """),

    Platform.EMAIL.value: textwrap.dedent("""\
        Subject: {subject}

        Hi there,

        {email_body}

        {email_cta}

        Best,
        {sender}
    """),
}


# ---------- helpers -----------------------------------------------------------

def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_]+", "-", slug).strip("-")[:80]


def _word_count(text: str) -> int:
    return len(text.split())


def _reading_time(word_count: int, wpm: int = 200) -> int:
    return max(1, round(word_count / wpm))


def _build_blog_sections(topic: Topic, angle: str) -> dict[str, str]:
    kws = ", ".join(topic.keywords[:5]) if topic.keywords else topic.title
    intro = (
        f"Content creation is evolving rapidly. In this post we explore "
        f"**{topic.title}** — a topic gaining traction in the "
        f"{topic.category or 'tech'} space. {angle}"
    )
    points = "\n".join(
        f"- **{kw.title()}**: Understanding the role of {kw} helps "
        f"you stay ahead of the curve."
        for kw in topic.keywords[:5]
    )
    tips = (
        "1. Start with thorough research before writing.\n"
        "2. Focus on actionable advice your audience can apply today.\n"
        "3. Use data and examples to back up your claims.\n"
        "4. Repurpose long-form content across platforms.\n"
        "5. Track performance and iterate."
    )
    conclusion = (
        f"The future of {topic.title} is bright. Start implementing "
        f"these insights today and measure your results. "
        f"Subscribe for more updates on {kws}."
    )
    return {"intro": intro, "key_points": points, "tips": tips, "conclusion": conclusion}


def _build_linkedin_parts(topic: Topic, angle: str) -> dict[str, str]:
    hook = f"🚀 {topic.title} is changing how we work — here's what most people miss:"
    body = (
        f"I've been researching {topic.title} extensively.\n\n"
        f"Here are 3 insights that stood out:\n\n"
        + "\n".join(
            f"→ {kw.title()}: {angle.split('.')[0] if angle else 'a key trend'}"
            for kw in topic.keywords[:3]
        )
    )
    tips = (
        "💡 Practical tips:\n"
        "1. Audit your current approach\n"
        "2. Start small, measure, then scale\n"
        "3. Share your learnings with your network"
    )
    cta = "What's your experience with this? Drop a comment below 👇"
    hashtags = " ".join(f"#{kw}" for kw in topic.keywords[:5])
    return {"hook": hook, "body": body, "tips_linkedin": tips, "cta": cta, "hashtags": hashtags}


def _build_instagram_parts(topic: Topic, angle: str) -> dict[str, str]:
    caption = (
        f"✨ {topic.title} ✨\n\n"
        f"{angle}\n\n"
        f"Save this post for later! 📌\n"
        f"Tag someone who needs to see this 👇"
    )
    hashtags_ig = " ".join(
        f"#{kw}" for kw in topic.keywords[:10]
    )
    return {"caption": caption, "hashtags_ig": hashtags_ig}


def _build_twitter_thread(topic: Topic, angle: str) -> dict[str, str]:
    lines = [
        f"🧵 THREAD: {topic.title}\n\nHere's what you need to know (1/{len(topic.keywords[:5]) + 1})",
    ]
    for i, kw in enumerate(topic.keywords[:5], start=1):
        lines.append(
            f"{i + 1}/{len(topic.keywords[:5]) + 1} — {kw.title()}: "
            f"{angle.split('.')[0] if angle else 'a key insight'}"
        )
    lines.append(
        f"{len(topic.keywords[:5]) + 2}/{len(topic.keywords[:5]) + 1} — "
        f"Found this useful? Follow for more on {topic.title}. 🔄 Retweet the first tweet!"
    )
    return {"thread": "\n\n".join(lines)}


def _build_email_parts(topic: Topic, angle: str) -> dict[str, str]:
    subject = f"Newsletter: {topic.title}"
    body = (
        f"This week we're diving into {topic.title}.\n\n"
        f"{angle}\n\n"
        f"Here's what you'll learn:\n"
        + "\n".join(f"  - {kw.title()}" for kw in topic.keywords[:5])
    )
    cta = (
        "Read the full article on our blog →\n"
        "Reply to this email with questions — I read every response."
    )
    return {"subject": subject, "email_body": body, "email_cta": cta, "sender": "Content Agent"}


_BUILDER_MAP = {
    Platform.BLOG.value: _build_blog_sections,
    Platform.LINKEDIN.value: _build_linkedin_parts,
    Platform.INSTAGRAM.value: _build_instagram_parts,
    Platform.TWITTER.value: _build_twitter_thread,
    Platform.EMAIL.value: _build_email_parts,
}


# ---------- main class -------------------------------------------------------

class ContentGenerator:
    """Generates platform-specific content from a Topic."""

    def __init__(self, sender_name: str = "Content Agent"):
        self.sender_name = sender_name

    def generate(
        self,
        topic: Topic,
        platform: str = Platform.BLOG.value,
    ) -> Post:
        """Generate a full Post for the given topic and platform."""
        angle = topic.suggested_angle or f"Exploring {topic.title}"

        builder = _BUILDER_MAP.get(platform, _BUILDER_MAP[Platform.BLOG.value])
        parts = builder(topic, angle)

        template = _TEMPLATES.get(platform, _TEMPLATES[Platform.BLOG.value])
        body = template.format(
            title=topic.title,
            angle=angle,
            tags=", ".join(topic.keywords[:5]),
            hashtags=" ".join(f"#{kw}" for kw in topic.keywords[:5]),
            hashtags_ig=" ".join(f"#{kw}" for kw in topic.keywords[:10]),
            sender=self.sender_name,
            reading_time=0,  # filled below
            **parts,
        )

        wc = _word_count(body)
        tags = topic.keywords[:5]
        hashtags = [f"#{kw}" for kw in topic.keywords[:5]]

        post = Post(
            topic_id=topic.id,
            platform=platform,
            title=topic.title,
            body=body.strip(),
            meta_title=f"{topic.title} — {platform.title()}",
            meta_description=f"Read about {topic.title}. {angle}"[:160],
            tags=tags,
            hashtags=hashtags,
            slug=_slugify(topic.title),
            word_count=wc,
            reading_time_min=_reading_time(wc),
            status=ContentStatus.DRAFT.value,
            created_at=datetime.utcnow().isoformat(),
        )
        return post

    def generate_all_platforms(self, topic: Topic) -> list[Post]:
        """Generate one post for every supported platform."""
        return [
            self.generate(topic, platform=plat.value)
            for plat in Platform
        ]
