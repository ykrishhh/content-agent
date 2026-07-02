"""
SEO optimizer — pure-Python keyword analysis and scoring.

No external dependencies. Works offline after topic research.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Optional

from .models import Post


# ---------- constants --------------------------------------------------------

_TITLE_MIN = 30
_TITLE_MAX = 60
_META_MIN = 120
_META_MAX = 160
_DESIRED_DENSITY = (1.0, 3.0)  # percent
_MIN_WORDS_BLOG = 300
_RECOMMENDED_WORDS = 1000


class SEOOptimizer:
    """Analyses and improves SEO quality of content."""

    def __init__(self):
        self.stop_words = frozenset(
            "a an the is it in to of for and or but with on at by from as "
            "this that are was were be been have has had do does did will "
            "would could should may might can shall not no nor so if then "
            "than too very just about above after again all also am any "
            "because before between both each few more most other some "
            "such into over own same only while during how what which who "
            "whom whose where when why".split()
        )

    # ----- public API ---------------------------------------------------------

    def optimize(self, post: Post) -> Post:
        """Run full optimization pipeline on a Post. Returns mutated Post."""
        primary_kw = post.tags[0] if post.tags else post.title.split()[0]

        post.meta_title = self._optimize_title(post.title, primary_kw)
        post.meta_description = self._optimize_meta_description(
            post.body, primary_kw
        )
        post.seo_score = self._calculate_score(post, primary_kw)
        post.status = "optimized"
        return post

    def analyze(self, post: Post) -> dict:
        """Return a detailed SEO analysis report."""
        primary_kw = post.tags[0] if post.tags else ""
        body_lower = post.body.lower()
        words = re.findall(r"[a-z0-9]+", body_lower)
        word_count = len(words)

        kw_density = 0.0
        kw_count = 0
        if primary_kw:
            kw_count = body_lower.count(primary_kw.lower())
            kw_density = (kw_count / max(word_count, 1)) * 100

        sentences = re.split(r"[.!?]+", post.body.strip())
        avg_sentence_len = (
            word_count / max(len([s for s in sentences if s.strip()]), 1)
        )

        headings = len(re.findall(r"^#{1,6}\s", post.body, re.MULTILINE))

        links_internal = len(re.findall(r"\[.*?\]\((?!http)", post.body))
        links_external = len(re.findall(r"https?://", post.body))

        images = len(re.findall(r"!\[.*?\]\(", post.body))

        return {
            "word_count": word_count,
            "reading_time_min": max(1, round(word_count / 200)),
            "primary_keyword": primary_kw,
            "keyword_count": kw_count,
            "keyword_density_pct": round(kw_density, 2),
            "density_in_range": (
                _DESIRED_DENSITY[0] <= kw_density <= _DESIRED_DENSITY[1]
            ),
            "meta_title_length": len(post.meta_title),
            "meta_title_ok": _TITLE_MIN <= len(post.meta_title) <= _TITLE_MAX,
            "meta_desc_length": len(post.meta_description),
            "meta_desc_ok": _META_MIN <= len(post.meta_description) <= _META_MAX,
            "avg_sentence_words": round(avg_sentence_len, 1),
            "heading_count": headings,
            "internal_links": links_internal,
            "external_links": links_external,
            "image_count": images,
            "readability_score": self._readability(post.body),
            "seo_score": self._calculate_score(post, primary_kw),
        }

    def keyword_suggestions(self, text: str, top_n: int = 15) -> list[str]:
        """Extract high-value keyword candidates from text."""
        words = re.findall(r"[a-zA-Z]{3,}", text.lower())
        filtered = [w for w in words if w not in self.stop_words]
        bigrams = []
        word_list = text.lower().split()
        for i in range(len(word_list) - 1):
            a, b = word_list[i], word_list[i + 1]
            if a not in self.stop_words and b not in self.stop_words:
                bigrams.append(f"{a} {b}")

        unigram_freq = Counter(filtered)
        bigram_freq = Counter(bigrams)

        combined: list[tuple[str, int]] = []
        for kw, cnt in unigram_freq.most_common(top_n * 2):
            combined.append((kw, cnt))
        for kw, cnt in bigram_freq.most_common(top_n):
            combined.append((kw, cnt * 2))

        combined.sort(key=lambda x: x[1], reverse=True)
        seen: set[str] = set()
        results: list[str] = []
        for kw, _ in combined:
            if kw not in seen:
                seen.add(kw)
                results.append(kw)
            if len(results) >= top_n:
                break
        return results

    def generate_schema_markup(self, post: Post) -> dict:
        """Generate JSON-LD structured data for the post."""
        return {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": post.title,
            "description": post.meta_description,
            "keywords": ", ".join(post.tags),
            "wordCount": post.word_count,
            "datePublished": post.created_at,
            "dateModified": post.created_at,
            "author": {"@type": "Organization", "name": "Content Agent"},
            "publisher": {
                "@type": "Organization",
                "name": "Content Agent",
            },
        }

    # ----- private ------------------------------------------------------------

    def _optimize_title(self, title: str, primary_kw: str) -> str:
        """Ensure title contains keyword and fits length bounds."""
        result = title.strip()
        if primary_kw and primary_kw.lower() not in result.lower():
            result = f"{result} — {primary_kw.title()}"
        if len(result) > _TITLE_MAX:
            result = result[: _TITLE_MAX - 3] + "..."
        return result

    def _optimize_meta_description(self, body: str, primary_kw: str) -> str:
        """Create a meta description within length bounds."""
        clean = re.sub(r"[#*_\[\]()>`]", "", body)
        sentences = [s.strip() for s in re.split(r"[.!?]+", clean) if s.strip()]
        desc = ""
        for s in sentences:
            candidate = f"{desc} {s}".strip() if desc else s
            if len(candidate) <= _META_MAX:
                desc = candidate
            else:
                break
        if not desc:
            desc = clean[:_META_MAX]
        if primary_kw and primary_kw.lower() not in desc.lower():
            desc = f"{desc} Learn about {primary_kw}."
        return desc[:_META_MAX]

    def _calculate_score(self, post: Post, primary_kw: str) -> float:
        """Weighted SEO score 0-100."""
        score = 0.0
        weights = {
            "title_length": 15,
            "meta_desc": 15,
            "keyword_density": 20,
            "word_count": 15,
            "readability": 15,
            "structure": 10,
            "freshness": 10,
        }

        # title length
        tl = len(post.meta_title)
        if _TITLE_MIN <= tl <= _TITLE_MAX:
            score += weights["title_length"]
        elif tl > 0:
            score += weights["title_length"] * 0.5

        # meta description
        ml = len(post.meta_description)
        if _META_MIN <= ml <= _META_MAX:
            score += weights["meta_desc"]
        elif ml > 0:
            score += weights["meta_desc"] * 0.5

        # keyword density
        words = post.body.lower().split()
        if primary_kw and words:
            density = (post.body.lower().count(primary_kw.lower()) / len(words)) * 100
            if _DESIRED_DENSITY[0] <= density <= _DESIRED_DENSITY[1]:
                score += weights["keyword_density"]
            elif 0 < density < _DESIRED_DENSITY[1] * 1.5:
                score += weights["keyword_density"] * 0.6

        # word count
        if post.word_count >= _RECOMMENDED_WORDS:
            score += weights["word_count"]
        elif post.word_count >= _MIN_WORDS_BLOG:
            score += weights["word_count"] * 0.7
        elif post.word_count > 0:
            score += weights["word_count"] * 0.3

        # readability
        readability = self._readability(post.body)
        if readability >= 60:
            score += weights["readability"]
        elif readability >= 40:
            score += weights["readability"] * 0.6

        # structure (headings)
        headings = len(re.findall(r"^#{1,6}\s", post.body, re.MULTILINE))
        if headings >= 3:
            score += weights["structure"]
        elif headings >= 1:
            score += weights["structure"] * 0.5

        # freshness (always max for new content)
        score += weights["freshness"]

        return round(min(score, 100.0), 1)

    def _readability(self, text: str) -> float:
        """Flesch Reading Ease score (0-100)."""
        sentences = max(len(re.split(r"[.!?]+", text.strip())), 1)
        words = text.split()
        num_words = max(len(words), 1)
        syllables = sum(self._count_syllables(w) for w in words)
        asl = num_words / sentences
        asw = syllables / num_words
        return round(206.835 - 1.015 * asl - 84.6 * asw, 1)

    def _count_syllables(self, word: str) -> int:
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
