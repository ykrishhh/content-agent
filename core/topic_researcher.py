"""
Topic research engine.

Fetches trending topics via web search, analyses competition,
and suggests content angles. Uses only requests + stdlib.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from typing import Optional

import requests

from .models import Topic

# ---------- helpers -----------------------------------------------------------

_STOP_WORDS = frozenset(
    "a an the is it in to of for and or but with on at by from as this that "
    "are was were be been have has had do does did will would could should "
    "may might can shall not no nor so if then than too very just about "
    "above after again all also am any because before between both each "
    "few more most other some such into over own same only while during "
    "how what which who whom whose where when why".split()
)


def _extract_keywords(text: str, top_n: int = 10) -> list[str]:
    """Pull the most frequent meaningful words from text."""
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    filtered = [w for w in words if w not in _STOP_WORDS]
    return [word for word, _ in Counter(filtered).most_common(top_n)]


def _simple_readability(text: str) -> float:
    """Flesch-like score (0-100). Higher = easier to read."""
    sentences = max(len(re.split(r"[.!?]+", text.strip())), 1)
    words_list = text.split()
    num_words = max(len(words_list), 1)
    syllables = sum(_count_syllables(w) for w in words_list)
    asl = num_words / sentences
    asw = syllables / num_words
    return round(206.835 - 1.015 * asl - 84.6 * asw, 1)


def _count_syllables(word: str) -> int:
    word = word.lower().strip()
    if len(word) <= 3:
        return 1
    vowels = "aeiou"
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


# ---------- main class -------------------------------------------------------

class TopicResearcher:
    """Discovers and analyses content topics from the web."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ContentAgent/0.1 (Termux)",
        })

    # ----- public API ---------------------------------------------------------

    def fetch_trending(
        self, niche: str, count: int = 10
    ) -> list[Topic]:
        """Return trending topics in *niche* via DuckDuckGo Lite + Reddit."""
        results: list[Topic] = []
        results.extend(self._search_ddg(niche, count=count))
        results.extend(self._search_reddit(nich=niche, count=count))
        return self._deduplicate(results)[:count]

    def analyze_competition(self, topic: Topic) -> Topic:
        """Score competition level for a topic (low / medium / high)."""
        query = f"{topic.title} {topic.description}".strip()
        if not query:
            topic.competition_level = "medium"
            return topic

        hits = self._ddg_count(query)
        if hits is None:
            topic.competition_level = "medium"
        elif hits < 5_000:
            topic.competition_level = "low"
        elif hits < 200_000:
            topic.competition_level = "medium"
        else:
            topic.competition_level = "high"
        return topic

    def suggest_angles(self, topic: Topic) -> Topic:
        """Generate a content angle suggestion from topic data."""
        if topic.competition_level == "low":
            topic.suggested_angle = (
                f"Beginner-friendly guide: {topic.title} — "
                "target underserved audience with step-by-step content."
            )
        elif topic.competition_level == "high":
            topic.suggested_angle = (
                f"Contrarian take: challenge common assumptions about "
                f"{topic.title} with data-driven insights."
            )
        else:
            topic.suggested_angle = (
                f"Practical walkthrough: {topic.title} — "
                "focus on actionable examples and real-world use cases."
            )
        return topic

    def research_topic(self, query: str, niche: str = "") -> Topic:
        """Full research pipeline: search → competition → angle → keywords."""
        topic = Topic(
            title=query,
            description=query,
            created_at=datetime.utcnow().isoformat(),
        )

        pages = self._search_ddg(query, count=5)
        if pages:
            titles = " ".join(p.title for p in pages)
            topic.description = titles[:500]
            topic.keywords = _extract_keywords(titles, top_n=8)
            topic.sources = [s for s in topic.sources if s]

        if niche:
            topic.category = niche

        topic = self.analyze_competition(topic)
        topic = self.suggest_angles(topic)
        topic.trending_score = self._estimate_trending(query)
        topic.status = "researched"
        return topic

    # ----- private: search backends -------------------------------------------

    def _search_ddg(self, query: str, count: int = 5) -> list[Topic]:
        """DuckDuckGo Lite HTML scraping (no API key needed)."""
        topics: list[Topic] = []
        try:
            resp = self.session.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query},
                timeout=10,
            )
            resp.raise_for_status()
            titles = re.findall(
                r'<a[^>]*class="result-link"[^>]*>(.*?)</a>',
                resp.text,
                re.DOTALL,
            )
            snippets = re.findall(
                r'<td class="result-snippet">(.*?)</td>',
                resp.text,
                re.DOTALL,
            )
            for i, title in enumerate(titles[:count]):
                clean_title = re.sub(r"<.*?>", "", title).strip()
                clean_snippet = (
                    re.sub(r"<.*?>", "", snippets[i]).strip()
                    if i < len(snippets)
                    else ""
                )
                topics.append(
                    Topic(
                        title=clean_title,
                        description=clean_snippet,
                        keywords=_extract_keywords(clean_title, top_n=5),
                    )
                )
        except requests.RequestException:
            pass
        return topics

    def _ddg_count(self, query: str) -> Optional[int]:
        """Estimate result count from DuckDuckGo."""
        try:
            resp = self.session.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query},
                timeout=10,
            )
            resp.raise_for_status()
            m = re.search(r"About ([\d,]+) results", resp.text)
            if m:
                return int(m.group(1).replace(",", ""))
            links = re.findall(r'class="result-link"', resp.text)
            return len(links)
        except requests.RequestException:
            return None

    def _search_reddit(self, nich: str, count: int = 5) -> list[Topic]:
        """Pull hot posts from relevant subreddits."""
        topics: list[Topic] = []
        try:
            resp = self.session.get(
                "https://www.reddit.com/search.json",
                params={"q": nich, "sort": "hot", "limit": count},
                headers={"User-Agent": "ContentAgent/0.1"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            for child in data.get("data", {}).get("children", [])[:count]:
                d = child.get("data", {})
                title = d.get("title", "")
                selftext = d.get("selftext", "")[:300]
                topics.append(
                    Topic(
                        title=title,
                        description=selftext,
                        sources=[
                            f"https://reddit.com{d.get('permalink', '')}"
                        ],
                        keywords=_extract_keywords(title, top_n=5),
                    )
                )
        except (requests.RequestException, json.JSONDecodeError):
            pass
        return topics

    # ----- private: utilities -------------------------------------------------

    def _estimate_trending(self, query: str) -> float:
        """Heuristic trending score 0-1 based on result density."""
        count = self._ddg_count(query)
        if count is None:
            return 0.5
        if count > 100_000:
            return 0.9
        if count > 10_000:
            return 0.7
        if count > 1_000:
            return 0.5
        return 0.3

    @staticmethod
    def _deduplicate(topics: list[Topic]) -> list[Topic]:
        seen_titles: set[str] = set()
        unique: list[Topic] = []
        for t in topics:
            key = t.title.lower().strip()
            if key not in seen_titles:
                seen_titles.add(key)
                unique.append(t)
        return unique
