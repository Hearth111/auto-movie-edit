"""Shared utility helpers for the auto_movie_edit package."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Iterable, Optional

_TIME_PATTERN = re.compile(
    r"^(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})(?:\.(?P<millis>\d{1,3}))?$"
)


class TimecodeError(ValueError):
    """Raised when a timecode string cannot be parsed."""


@dataclass(slots=True)
class Timecode:
    """Represents a parsed timecode."""

    hours: int
    minutes: int
    seconds: int
    milliseconds: int = 0

    def to_timedelta(self) -> timedelta:
        """Convert the timecode into :class:`datetime.timedelta`."""

        return timedelta(
            hours=self.hours,
            minutes=self.minutes,
            seconds=self.seconds,
            milliseconds=self.milliseconds,
        )

    def to_seconds(self) -> float:
        """Return the total seconds represented by the timecode."""

        td = self.to_timedelta()
        return td.total_seconds()

    def to_string(self) -> str:
        """Render the timecode as ``HH:MM:SS.mmm`` string."""

        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}.{self.milliseconds:03d}"


def parse_timecode(value: str | None) -> Optional[Timecode]:
    """Parse a timecode string into a :class:`Timecode` instance.

    Args:
        value: The string value to parse. ``None`` or an empty string returns ``None``.

    Raises:
        TimecodeError: If the value cannot be parsed as a timecode.
    """

    if value is None:
        return None

    # ★★★ ここが修正点です ★★★
    # SRTファイルのカンマ区切りに対応するため、ピリオドに置換します
    value = value.strip().replace(",", ".")
    # ★★★ 修正ここまで ★★★
    
    if not value:
        return None

    match = _TIME_PATTERN.match(value)
    if not match:
        raise TimecodeError(f"Invalid timecode: {value!r}")

    millis = match.group("millis")
    # ミリ秒が3桁に満たない場合（例: .5）でも正しく処理するように調整
    if millis:
        milliseconds = int(millis.ljust(3, '0'))
    else:
        milliseconds = 0
        
    return Timecode(
        hours=int(match.group("hour")),
        minutes=int(match.group("minute")),
        seconds=int(match.group("second")),
        milliseconds=milliseconds,
    )


def parse_mapping(raw: Any) -> Dict[str, Any]:
    """Parse a mapping definition stored as JSON or semi-colon separated pairs.

    Args:
        raw: The raw value, typically a string stored in a spreadsheet cell.

    Returns:
        A dictionary representing the mapping. Unknown formats yield an empty dict.
    """

    if raw is None:
        return {}

    if isinstance(raw, dict):
        return dict(raw)

    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}

        # Try JSON first.
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            pairs: Dict[str, Any] = {}
            for chunk in text.split(";"):
                chunk = chunk.strip()
                if not chunk or "=" not in chunk:
                    continue
                key, value = chunk.split("=", 1)
                pairs[key.strip()] = value.strip()
            return pairs
        else:
            if isinstance(parsed, dict):
                return parsed
            return {}

    return {}


def ensure_list(value: Any) -> list[Any]:
    """Ensure a value is returned as a list, splitting comma separated strings."""

    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, str):
        chunks = [chunk.strip() for chunk in value.split(",")]
        return [chunk for chunk in chunks if chunk]

    return [value]


def load_json(path: str | "os.PathLike[str]") -> Any:
    """Load a JSON document from ``path``."""

    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path: str | "os.PathLike[str]", data: Any) -> None:
    """Write a JSON document to ``path`` with UTF-8 encoding."""

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def iter_nonempty(rows: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    """Yield only rows that contain at least one non-empty value."""

    for row in rows:
        if not row:
            continue
        for value in row.values():
            if value not in (None, ""):
                yield row
                break


def count_hiragana(text: str) -> int:
    """Count the number of Hiragana characters in ``text``."""

    return sum(1 for char in text if "\u3040" <= char <= "\u309f")


def contains_hiragana(text: str | None) -> bool:
    """Return ``True`` if the given text contains at least one Hiragana character."""

    if not text:
        return False
    return count_hiragana(text) > 0