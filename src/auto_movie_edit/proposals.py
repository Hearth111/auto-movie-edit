"""Learning utilities for maintaining AI proposal statistics."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Tuple

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .language import LanguageAnalyzer

from .utils import TimecodeError, parse_timecode

__all__ = [
    "ProposalModel",
    "ProposalSuggestions",
    "ProposalCandidate",
    "update_proposal_model",
]


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9ぁ-んァ-ヶ一-龯ー]+")
_APPROVAL_POSITIVE = {
    "true",
    "1",
    "yes",
    "y",
    "approved",
    "ok",
    "承認",
    "採用",
    "可",
}
_APPROVAL_NEGATIVE = {
    "false",
    "0",
    "no",
    "n",
    "rejected",
    "却下",
    "不採用",
    "否",
}


@dataclass(slots=True)
class ProposalCandidate:
    """Represents a ranked proposal candidate."""

    identifier: str
    score: float
    base_score: float
    wins: int
    losses: int
    last_seen: Any | None = None
    last_row_index: int | None = None
    last_position: float | None = None


@dataclass(slots=True)
class ProposalSuggestions:
    """Container for ranked proposal candidates by category."""

    items: Dict[str, List[ProposalCandidate]] = field(default_factory=dict)

    def top(self, category: str, limit: int = 1) -> List[str]:
        """Return the best ``limit`` entries for ``category``."""

        ranked = self.items.get(category, [])
        return [candidate.identifier for candidate in ranked[:limit]]

    def top_candidates(self, category: str, limit: int = 1) -> List[ProposalCandidate]:
        """Return the best candidates including their scores."""

        ranked = self.items.get(category, [])
        return ranked[:limit]

    def best(self, category: str) -> ProposalCandidate | None:
        """Return the single best candidate if available."""

        ranked = self.items.get(category, [])
        return ranked[0] if ranked else None

    def has_data(self) -> bool:
        """Return ``True`` if at least one category has proposals."""

        return any(self.items.values())


class ProposalModel:
    """Maintains lightweight statistics for AI proposal suggestions."""

    def __init__(
        self,
        stats: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] | None = None,
        processed: Iterable[str] | None = None,
        version: int = 1,
    ) -> None:
        self.version = version
        self.stats: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = stats or {}
        self._processed_order: List[str] = list(processed or [])
        self._processed: set[str] = set(self._processed_order)
        self.max_history = 5000

    @classmethod
    def load(cls, path: Path | str) -> "ProposalModel":
        """Load a model from ``path`` if it exists, otherwise return an empty model."""

        path = Path(path)
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):  # pragma: no cover - defensive
            return cls()
        return cls(
            stats=raw.get("keywords", {}),
            processed=raw.get("processed", []),
            version=raw.get("version", 1),
        )

    def save(self, path: Path | str) -> None:
        """Persist the model to ``path``."""

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "version": self.version,
            "updated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "keywords": self.stats,
            "processed": self._processed_order[-self.max_history :],
        }
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------
    def update_from_history(self, history: Iterable[Dict[str, Any]]) -> bool:
        """Update statistics using freshly generated history entries."""

        changed = False
        for entry in history:
            entry_id = self._entry_id(entry)
            if entry_id in self._processed:
                continue
            tokens = self._tokenize(entry.get("subtitle"))
            tokens.append("__global__")
            approved = self._normalize_approval(entry.get("notes", {}).get("approval"))
            timestamp = entry.get("timestamp")
            row_index = self._int_value(entry.get("row_index"))
            position = self._timeline_position(entry)

            recorded = False
            recorded |= self._record_items(
                tokens,
                "telop",
                [entry.get("telop")],
                approved,
                timestamp,
                row_index,
                position,
            )
            recorded |= self._record_items(
                tokens,
                "pack",
                entry.get("packs", []),
                approved,
                timestamp,
                row_index,
                position,
            )
            recorded |= self._record_items(
                tokens,
                "asset",
                self._resolve_assets(entry.get("objects", [])),
                approved,
                timestamp,
                row_index,
                position,
            )
            recorded |= self._record_items(
                tokens,
                "fx",
                [fx.get("fx_id") for fx in entry.get("fx", [])],
                approved,
                timestamp,
                row_index,
                position,
            )

            if recorded:
                changed = True
                self._register_processed(entry_id)
        return changed

    # ------------------------------------------------------------------
    # Suggestions
    # ------------------------------------------------------------------
    def suggest(
        self,
        subtitle: str | None,
        limit: int = 3,
        analyzer: "LanguageAnalyzer" | None = None,
        row_index: int | None = None,
        position_seconds: float | None = None,
    ) -> ProposalSuggestions:
        """Return ranked proposal candidates for a subtitle."""

        tokens = self._tokenize(subtitle, analyzer=analyzer)
        tokens.append("__global__")
        suggestions: Dict[str, List[ProposalCandidate]] = {}
        for category in ("telop", "pack", "asset", "fx"):
            aggregated = self._collect_candidates(tokens, category)
            ranked = self._rank_candidates(
                aggregated,
                limit,
                row_index=row_index,
                position=position_seconds,
            )
            if ranked:
                suggestions[category] = ranked
        return ProposalSuggestions(items=suggestions)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _record_items(
        self,
        tokens: List[str],
        category: str,
        items: Iterable[Any],
        approved: bool | None,
        timestamp: str | None,
        row_index: int | None,
        position: float | None,
    ) -> bool:
        recorded = False
        for item in items:
            identifier = self._normalize_identifier(item)
            if not identifier:
                continue
            for token in tokens:
                if self._record(
                    token,
                    category,
                    identifier,
                    approved,
                    timestamp,
                    row_index,
                    position,
                ):
                    recorded = True
        return recorded

    def _record(
        self,
        token: str,
        category: str,
        identifier: str,
        approved: bool | None,
        timestamp: str | None,
        row_index: int | None,
        position: float | None,
    ) -> bool:
        keyword_stats = self.stats.setdefault(token, {})
        category_stats = keyword_stats.setdefault(category, {})
        item_stats = category_stats.setdefault(
            identifier,
            {
                "wins": 0,
                "losses": 0,
                "total": 0,
                "last_seen": timestamp,
                "last_row_index": row_index,
                "last_position": position,
            },
        )

        item_stats["total"] = int(item_stats.get("total", 0)) + 1
        if approved is True:
            item_stats["wins"] = int(item_stats.get("wins", 0)) + 1
        elif approved is False:
            item_stats["losses"] = int(item_stats.get("losses", 0)) + 1
        if timestamp:
            item_stats["last_seen"] = timestamp
        if row_index is not None:
            try:
                current_index = int(row_index)
            except (TypeError, ValueError):
                current_index = None
            if current_index is not None:
                previous_index = self._int_value(item_stats.get("last_row_index"))
                if previous_index is None or current_index >= previous_index:
                    item_stats["last_row_index"] = current_index
        if position is not None:
            try:
                current_position = float(position)
            except (TypeError, ValueError):
                current_position = None
            if current_position is not None:
                previous_position = self._float_value(item_stats.get("last_position"))
                if previous_position is None or current_position >= previous_position:
                    item_stats["last_position"] = current_position
        return True

    def _collect_candidates(
        self, tokens: List[str], category: str
    ) -> Dict[str, Dict[str, Any]]:
        aggregated: Dict[str, Dict[str, Any]] = {}
        for token in tokens:
            category_stats = self.stats.get(token, {}).get(category, {})
            for identifier, stats in category_stats.items():
                target = aggregated.setdefault(
                    identifier,
                    {
                        "wins": 0,
                        "losses": 0,
                        "total": 0,
                        "last_seen": None,
                        "last_row_index": None,
                        "last_position": None,
                    },
                )
                target["wins"] += int(stats.get("wins", 0))
                target["losses"] += int(stats.get("losses", 0))
                target["total"] += int(stats.get("total", 0))
                timestamp = stats.get("last_seen")
                if timestamp and (
                    not target["last_seen"]
                    or timestamp > target["last_seen"]
                ):
                    target["last_seen"] = timestamp
                row_index = self._int_value(stats.get("last_row_index"))
                if row_index is not None:
                    existing_row = target.get("last_row_index")
                    if existing_row is None or row_index > existing_row:
                        target["last_row_index"] = row_index
                position = self._float_value(stats.get("last_position"))
                if position is not None:
                    existing_position = target.get("last_position")
                    if existing_position is None or position > existing_position:
                        target["last_position"] = position
        return aggregated

    def _rank_candidates(
        self,
        candidates: Dict[str, Dict[str, Any]],
        limit: int,
        row_index: int | None,
        position: float | None,
    ) -> List[ProposalCandidate]:
        scored: List[Tuple[ProposalCandidate, Dict[str, Any]]] = []
        for identifier, stats in candidates.items():
            base_score = self._score_candidate(stats)
            if base_score <= 0:
                continue
            weight = self._context_weight(stats, row_index=row_index, position=position)
            adjusted_score = base_score * weight
            if adjusted_score <= 0:
                continue
            candidate = ProposalCandidate(
                identifier=identifier,
                score=round(adjusted_score, 4),
                base_score=round(base_score, 4),
                wins=int(stats.get("wins", 0)),
                losses=int(stats.get("losses", 0)),
                last_seen=stats.get("last_seen"),
                last_row_index=self._int_value(stats.get("last_row_index")),
                last_position=self._float_value(stats.get("last_position")),
            )
            scored.append((candidate, stats))

        scored.sort(
            key=lambda item: (
                item[0].score,
                item[0].base_score,
                item[0].wins,
                -item[0].losses,
                self._timestamp_value(item[1].get("last_seen")),
                item[0].identifier,
            ),
            reverse=True,
        )

        return [candidate for candidate, _ in scored[:limit]]

    def _context_weight(
        self,
        stats: Dict[str, Any],
        *,
        row_index: int | None,
        position: float | None,
    ) -> float:
        weight = 1.0
        last_position = self._float_value(stats.get("last_position"))
        if position is not None and last_position is not None:
            gap = abs(position - last_position)
            if gap < 30.0:
                weight *= max(0.2, gap / 30.0)
        last_row = self._int_value(stats.get("last_row_index"))
        if row_index is not None and last_row is not None:
            row_gap = abs(int(row_index) - last_row)
            if row_gap <= 3:
                weight *= max(0.3, row_gap / 3.0)
        return weight

    @staticmethod
    def _score_candidate(stats: Dict[str, Any]) -> float:
        wins = float(stats.get("wins", 0))
        losses = float(stats.get("losses", 0))
        total = float(stats.get("total", wins + losses))
        if total <= 0:
            return 0.0
        base = wins - losses
        confidence = wins / total
        return base + confidence

    @staticmethod
    def _int_value(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _float_value(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _timestamp_value(value: Any) -> float:
        if not value:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value)
        if not text:
            return 0.0
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
        return dt.timestamp()

    @staticmethod
    def _timeline_position(entry: Dict[str, Any]) -> float | None:
        start = entry.get("start")
        if not start:
            return None
        try:
            timecode = parse_timecode(str(start))
        except TimecodeError:
            return None
        if timecode is None:
            return None
        return timecode.to_seconds()

    @staticmethod
    def _tokenize(
        text: str | None,
        analyzer: "LanguageAnalyzer" | None = None,
    ) -> List[str]:
        if not text:
            return []
        tokens: List[str] = []
        if analyzer is not None:
            tokens = analyzer.tokenize(text)
        if not tokens:
            tokens = _TOKEN_PATTERN.findall(text)
        if not tokens:
            tokens = [text.strip()]
        return tokens

    @staticmethod
    def _resolve_assets(objects: Iterable[Dict[str, Any]]) -> List[str]:
        resolved: List[str] = []
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            resolved_id = obj.get("resolved_asset") or obj.get("identifier")
            if resolved_id:
                resolved.append(str(resolved_id))
        return resolved

    @staticmethod
    def _normalize_identifier(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value).strip() or None

    @staticmethod
    def _entry_id(entry: Dict[str, Any]) -> str:
        timestamp = entry.get("timestamp") or ""
        row_index = entry.get("row_index")
        telop = entry.get("telop") or ""
        return f"{timestamp}|{row_index}|{telop}"

    @staticmethod
    def _normalize_approval(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in _APPROVAL_POSITIVE:
            return True
        if text in _APPROVAL_NEGATIVE:
            return False
        return None

    def _register_processed(self, entry_id: str) -> None:
        if entry_id in self._processed:
            return
        self._processed.add(entry_id)
        self._processed_order.append(entry_id)
        if len(self._processed_order) > self.max_history:
            oldest = self._processed_order.pop(0)
            self._processed.discard(oldest)


def update_proposal_model(
    history: Iterable[Dict[str, Any]], base_path: Path | str
) -> Path | None:
    """Update the proposal model stored under ``base_path`` using ``history``."""

    history = list(history)
    if not history:
        return None

    base_path = Path(base_path)
    model_path = base_path / "ai" / "proposal_model.json" if base_path.is_dir() else base_path

    model = ProposalModel.load(model_path)
    if model.update_from_history(history):
        model.save(model_path)
        return model_path
    return model_path if model_path.exists() else None

