"""Language analysis utilities for subtitle-driven AI suggestions."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import List, Sequence

try:  # pragma: no cover - optional dependency loading
    from fugashi import Tagger  # type: ignore
except Exception:  # pragma: no cover - defensive
    Tagger = None  # type: ignore

__all__ = ["LanguageAnalyzer", "SubtitleAnalysis", "SubtitleInsight"]


_WORD_PATTERN = re.compile(r"[A-Za-z0-9ぁ-んァ-ヶ一-龯ー]+")
_PRIMARY_POS = {"名詞", "動詞", "形容詞", "副詞"}


@dataclass(slots=True)
class SubtitleInsight:
    """Lightweight description of a subtitle line extracted from analysis."""

    keywords: List[str]
    emphasis: str | None = None


@dataclass(slots=True)
class SubtitleAnalysis:
    """Aggregate information derived from a collection of subtitles."""

    insights: List[SubtitleInsight]
    global_keywords: List[str]


class LanguageAnalyzer:
    """High quality text analyzer backed by Fugashi and UniDic-lite."""

    def __init__(self) -> None:
        self._tagger: Tagger | None = None  # type: ignore[assignment]
        self._tagger_error: Exception | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def analyze_subtitles(
        self,
        subtitles: Sequence[str],
        keyword_limit: int = 5,
        global_limit: int = 10,
    ) -> SubtitleAnalysis:
        """Return rich insights extracted from ``subtitles``.

        ``keyword_limit`` controls the maximum number of keywords kept for
        each subtitle line, while ``global_limit`` restricts the number of
        top-level topics aggregated across the entire subtitle script.
        """

        insights: List[SubtitleInsight] = []
        global_counter: Counter[str] = Counter()

        for text in subtitles:
            keywords = self.extract_keywords(text, limit=keyword_limit)
            if keywords:
                global_counter.update(keywords)
            emphasis = self._detect_emphasis(text)
            insights.append(SubtitleInsight(keywords=keywords, emphasis=emphasis))

        global_keywords = [word for word, _ in global_counter.most_common(global_limit)]
        return SubtitleAnalysis(insights=insights, global_keywords=global_keywords)

    def extract_keywords(self, text: str | None, limit: int = 5) -> List[str]:
        """Extract ``limit`` key terms from ``text`` using morphological analysis."""

        if not text:
            return []

        tokens = self.tokenize(text)
        if not tokens:
            tokens = [token.lower() for token in _WORD_PATTERN.findall(text)]
        if not tokens:
            return []

        counter: Counter[str] = Counter()
        for token in tokens:
            if not token:
                continue
            counter[token] += 1

        keywords = [word for word, _ in counter.most_common(limit)]
        return keywords

    def tokenize(self, text: str | None) -> List[str]:
        """Tokenize ``text`` using Fugashi, falling back to regex segmentation."""

        if not text:
            return []

        self._ensure_tagger()
        if self._tagger is None:
            return [token.lower() for token in _WORD_PATTERN.findall(text)]

        tokens: List[str] = []
        for word in self._tagger(text):
            pos = getattr(word.feature, "pos1", None) or getattr(word.feature, "pos", None)
            if pos and pos not in _PRIMARY_POS:
                continue
            lemma = getattr(word.feature, "lemma", None)
            surface = word.surface.strip()
            candidate = (lemma or surface or "").strip()
            if not candidate:
                continue
            tokens.append(candidate.lower())
        return tokens

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def detect_tone(self, text: str | None) -> str | None:
        """Public wrapper for tone detection used by other modules."""

        return self._detect_emphasis(text)

    def _ensure_tagger(self) -> None:
        if self._tagger or self._tagger_error is not None:
            return
        if Tagger is None:
            self._tagger_error = RuntimeError("Fugashi is not available")
            return
        try:
            self._tagger = Tagger()
        except Exception as exc:  # pragma: no cover - defensive
            self._tagger_error = exc

    @staticmethod
    def _detect_emphasis(text: str | None) -> str | None:
        if not text:
            return None
        stripped = text.strip()
        if not stripped:
            return None
        if "？" in stripped or "?" in stripped:
            return "質問調"
        if stripped.endswith("！") or stripped.endswith("!"):
            return "強調"
        if "..." in stripped or "…" in stripped:
            return "余韻"
        return None

