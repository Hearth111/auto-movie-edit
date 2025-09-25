"""Language analysis utilities for subtitle-driven AI suggestions."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import math
import re
from functools import lru_cache
from typing import Dict, List, Sequence

try:  # pragma: no cover - optional dependency loading
    from fugashi import Tagger  # type: ignore
except Exception:  # pragma: no cover - defensive
    Tagger = None  # type: ignore

__all__ = ["LanguageAnalyzer", "SubtitleAnalysis", "SubtitleInsight"]


_WORD_PATTERN = re.compile(r"[A-Za-z0-9ぁ-んァ-ヶ一-龯ー]+")
_PRIMARY_POS = {"名詞", "動詞", "形容詞", "副詞"}

_QUESTION_SUFFIXES = (
    "か",
    "かな",
    "かい",
    "かしら",
    "でしょうか",
    "ですか",
    "だろうか",
    "なの",
)

_TONE_KEYWORD_SCORES: Dict[str, Dict[str, float]] = {
    "質問調": {
        "か": 0.4,
        "かな": 0.8,
        "かい": 0.8,
        "かしら": 1.0,
        "だろうか": 1.1,
        "でしょうか": 1.3,
        "ですか": 1.2,
        "なの": 0.6,
        "何": 0.5,
        "どう": 0.5,
        "なぜ": 0.7,
    },
    "強調": {
        "絶対": 1.5,
        "本当": 1.1,
        "ほんと": 1.0,
        "ほんとう": 1.0,
        "めっちゃ": 1.3,
        "超": 1.1,
        "すごい": 0.9,
        "すごく": 1.2,
        "マジ": 1.0,
        "断言": 1.2,
        "必ず": 1.2,
        "最強": 1.1,
        "重要": 0.9,
        "強調": 1.0,
    },
    "余韻": {
        "かな": 0.6,
        "かも": 0.8,
        "かしら": 0.5,
        "かなぁ": 1.0,
        "かなー": 0.8,
        "かもね": 1.0,
        "だよね": 0.6,
        "かもしれ": 1.1,
        "と思う": 0.7,
        "気がする": 0.9,
    },
    "喜び": {
        "嬉しい": 2.0,
        "たのしい": 1.5,
        "楽しい": 1.5,
        "最高": 1.4,
        "やった": 1.6,
        "よかった": 1.3,
        "助かる": 1.1,
        "ありがとう": 1.4,
        "感謝": 1.2,
        "幸せ": 1.6,
    },
    "悲しみ": {
        "悲しい": 2.0,
        "つらい": 1.7,
        "さみしい": 1.5,
        "最悪": 1.1,
        "泣": 1.4,
        "しんどい": 1.3,
        "辛い": 1.7,
        "寂しい": 1.5,
        "落ち込": 1.6,
        "ショック": 1.3,
    },
    "怒り": {
        "怒": 1.6,
        "許せない": 2.0,
        "ふざけるな": 1.8,
        "ムカつく": 1.9,
        "信じられない": 1.4,
        "なんで": 0.8,
        "ひどい": 1.3,
        "納得できない": 1.6,
    },
    "驚き": {
        "えっ": 1.5,
        "まさか": 1.6,
        "嘘": 1.3,
        "ほんと": 1.0,
        "信じられない": 1.6,
        "びっくり": 1.7,
        "驚": 1.5,
        "なにそれ": 1.4,
    },
}

_CATEGORY_PRIORITY = [
    "強調",
    "質問調",
    "喜び",
    "驚き",
    "怒り",
    "悲しみ",
    "余韻",
]


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
        self._tokenize_cached = lru_cache(maxsize=1024)(self._tokenize_internal)
        self._keywords_cached = lru_cache(maxsize=512)(self._extract_keywords_internal)
        self._tone_cached = lru_cache(maxsize=512)(self._compute_tone)

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

        normalized = self._normalize_text(text)
        if not normalized:
            return []
        if limit <= 0:
            return []
        keywords = list(self._keywords_cached(normalized))
        if limit < len(keywords):
            return keywords[:limit]
        return keywords

    def tokenize(self, text: str | None) -> List[str]:
        """Tokenize ``text`` using Fugashi, falling back to regex segmentation."""

        normalized = self._normalize_text(text)
        if not normalized:
            return []
        return list(self._tokenize_cached(normalized))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def detect_tone(self, text: str | None) -> str | None:
        """Public wrapper for tone detection used by other modules."""

        normalized = self._normalize_text(text)
        if not normalized:
            return None
        return self._tone_cached(normalized)

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

    def _detect_emphasis(self, text: str | None) -> str | None:
        return self.detect_tone(text)

    @staticmethod
    def _normalize_text(text: str | None) -> str:
        if text is None:
            return ""
        stripped = text.strip()
        if not stripped:
            return ""
        return re.sub(r"\s+", " ", stripped)

    def _tokenize_internal(self, normalized_text: str) -> tuple[str, ...]:
        if not normalized_text:
            return ()

        self._ensure_tagger()
        if self._tagger is None:
            return tuple(token.lower() for token in _WORD_PATTERN.findall(normalized_text))

        tokens: List[str] = []
        for word in self._tagger(normalized_text):
            pos = getattr(word.feature, "pos1", None) or getattr(word.feature, "pos", None)
            if pos and pos not in _PRIMARY_POS:
                continue
            lemma = getattr(word.feature, "lemma", None)
            surface = word.surface.strip()
            candidate = (lemma or surface or "").strip()
            if not candidate:
                continue
            tokens.append(candidate.lower())

        if not tokens:
            return tuple(token.lower() for token in _WORD_PATTERN.findall(normalized_text))
        return tuple(tokens)

    def _extract_keywords_internal(self, normalized_text: str) -> tuple[str, ...]:
        if not normalized_text:
            return ()

        tokens = list(self._tokenize_cached(normalized_text))
        if not tokens:
            tokens = [token.lower() for token in _WORD_PATTERN.findall(normalized_text)]
        if not tokens:
            return ()

        counter: Counter[str] = Counter(tokens)
        return tuple(word for word, _ in counter.most_common())

    def _compute_tone(self, normalized_text: str) -> str | None:
        if not normalized_text:
            return None

        stripped = normalized_text

        normalized_tail = re.sub(r"[\s。．\.！!？?〜ー…]*$", "", stripped)
        tokens = list(self._tokenize_cached(stripped))
        if not tokens:
            tokens = [token.lower() for token in _WORD_PATTERN.findall(stripped)]
        counter = Counter(tokens)
        scores: Dict[str, float] = defaultdict(float)

        # Punctuation based heuristics
        if "？" in stripped or "?" in stripped:
            scores["質問調"] += 2.5
        if stripped.endswith("？") or stripped.endswith("?"):
            scores["質問調"] += 1.5
        if "！" in stripped or "!" in stripped:
            emphasis_boost = 1.2 + 0.3 * (stripped.count("！") + stripped.count("!"))
            scores["強調"] += emphasis_boost
            scores["驚き"] += emphasis_boost * 0.3
        if "..." in stripped or "…" in stripped:
            scores["余韻"] += 1.2
        if stripped.endswith("〜") or stripped.endswith("ー"):
            scores["余韻"] += 0.8
        if "！？" in stripped or "?!" in stripped:
            scores["驚き"] += 1.4
            scores["強調"] += 0.6

        # Tail-based linguistic cues
        for suffix in _QUESTION_SUFFIXES:
            if normalized_tail.endswith(suffix):
                scores["質問調"] += 0.9 + 0.15 * len(suffix)
        if normalized_tail.endswith("かな") or normalized_tail.endswith("かも"):
            scores["余韻"] += 0.6

        # Keyword-based weighting from morphological tokens
        for token, count in counter.items():
            for category, keyword_map in _TONE_KEYWORD_SCORES.items():
                for keyword, weight in keyword_map.items():
                    if keyword in token:
                        scores[category] += weight * count

        # Soft sentiment modifier based on positive/negative balance
        positive = scores.get("喜び", 0.0)
        negative = scores.get("悲しみ", 0.0) + scores.get("怒り", 0.0)
        if positive > 0 and positive > negative:
            scores["喜び"] += math.log1p(positive)
        if negative > 0:
            scores["悲しみ"] += math.log1p(scores.get("悲しみ", 0.0)) * 0.5
            scores["怒り"] += math.log1p(scores.get("怒り", 0.0)) * 0.5

        if not scores:
            return None

        best_category = max(scores.items(), key=lambda item: item[1])
        if best_category[1] < 1.0:
            return None

        # Resolve ties by category priority to keep behaviour deterministic.
        best_score = best_category[1]
        tied_categories = [
            category for category, score in scores.items() if abs(score - best_score) < 0.25
        ]
        if len(tied_categories) > 1:
            for category in _CATEGORY_PRIORITY:
                if category in tied_categories:
                    return category
        return best_category[0]

