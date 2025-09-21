"""SRT (SubRip) subtitle parser used for timeline scaffolding."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List

from .utils import Timecode, TimecodeError, parse_timecode


@dataclass(slots=True)
class SrtEntry:
    """Represents a single SRT subtitle block."""

    index: int
    start: Timecode
    end: Timecode
    text: str


class SrtParseError(RuntimeError):
    """Raised when an SRT file cannot be parsed."""


def _chunks(lines: Iterable[str]) -> Iterator[list[str]]:
    chunk: list[str] = []
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped == "":
            if chunk:
                yield chunk
                chunk = []
            continue
        chunk.append(stripped)
    if chunk:
        yield chunk


def parse_srt(path: str | Path) -> List[SrtEntry]:
    """Parse an SRT file and return a list of entries."""

    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SrtParseError(f"SRT file not found: {path}") from exc

    entries: list[SrtEntry] = []
    for raw_chunk in _chunks(text.splitlines()):
        if not raw_chunk:
            continue
        try:
            index = int(raw_chunk[0])
        except ValueError as exc:
            raise SrtParseError(f"Invalid SRT index line: {raw_chunk[0]!r}") from exc
        if len(raw_chunk) < 2:
            raise SrtParseError(f"Missing timecode line for index {index}")
        times = raw_chunk[1]
        if "-->" not in times:
            raise SrtParseError(f"Invalid timecode line for index {index}: {times!r}")
        start_text, end_text = [part.strip() for part in times.split("-->")]
        try:
            start = parse_timecode(start_text)
            end = parse_timecode(end_text)
        except TimecodeError as exc:
            raise SrtParseError(str(exc)) from exc
        if start is None or end is None:
            raise SrtParseError(f"Incomplete timecode for index {index}")
        text_lines = raw_chunk[2:]
        entries.append(SrtEntry(index=index, start=start, end=end, text="\n".join(text_lines)))
    return entries
