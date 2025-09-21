"""Generation of simplified YMM4 project structures."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .models import TimelineRow, WorkbookData
from .utils import contains_hiragana, dump_json


class BuildWarning:
    """Represents a warning produced during project build."""

    def __init__(self, row_index: int | None, message: str) -> None:
        self.row_index = row_index
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {"row": self.row_index, "message": self.message}


class ProjectBuilder:
    """Transforms workbook data into a serialisable project representation."""

    def __init__(self, data: WorkbookData) -> None:
        self.data = data
        self.warnings: list[BuildWarning] = []

    def build(self) -> dict[str, Any]:
        timeline_entries: list[dict[str, Any]] = []
        for row in self.data.timeline:
            entry = self._build_row(row)
            timeline_entries.append(entry)
        return {
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "telop_patterns": {key: asdict(value) for key, value in self.data.telop_patterns.items()},
            "assets": {key: asdict(value) for key, value in self.data.assets.items()},
            "packs": {key: asdict(value) for key, value in self.data.packs.items()},
            "fx_presets": {key: asdict(value) for key, value in self.data.fx_presets.items()},
            "layers": {key: asdict(value) for key, value in self.data.layers.items()},
            "timeline": timeline_entries,
        }

    def _build_row(self, row: TimelineRow) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "index": row.index,
            "start": row.start.to_string() if row.start else None,
            "end": row.end.to_string() if row.end else None,
            "subtitle": row.subtitle,
            "telop": None,
            "packs": row.packs,
            "objects": [],
            "fx": [],
            "notes": row.notes,
        }
        if row.start and row.end:
            entry["duration_seconds"] = max(0.0, row.end.to_seconds() - row.start.to_seconds())

        if row.telop:
            pattern = self.data.telop_patterns.get(row.telop)
            if pattern:
                entry["telop"] = {
                    "pattern_id": pattern.pattern_id,
                    "source": pattern.source,
                    "overrides": pattern.overrides,
                    "text": row.subtitle,
                    "scale": 1.0,
                }
            else:
                self._warn(row, f"Telop pattern not found: {row.telop}")

        for obj in row.objects:
            asset = self.data.assets.get(obj.identifier)
            if not asset:
                self._warn(row, f"Asset not found: {obj.identifier}")
            entry["objects"].append(
                {
                    "role": obj.role,
                    "identifier": obj.identifier,
                    "layer": obj.layer,
                    "resolved": asdict(asset) if asset else None,
                }
            )

        for fx in row.fxs:
            preset = self.data.fx_presets.get(fx.fx_id)
            if not preset:
                self._warn(row, f"FX preset not found: {fx.fx_id}")
            entry["fx"].append(
                {
                    "fx_id": fx.fx_id,
                    "parameters": fx.parameters,
                    "resolved": asdict(preset) if preset else None,
                }
            )

        return entry

    def _warn(self, row: TimelineRow, message: str) -> None:
        self.warnings.append(BuildWarning(row.index, message))


def build_project(data: WorkbookData) -> Tuple[dict[str, Any], List[BuildWarning]]:
    """Generate a project representation and collect warnings."""

    builder = ProjectBuilder(data)
    project = builder.build()
    return project, builder.warnings


def write_outputs(project: dict[str, Any], warnings: List[BuildWarning], output_dir: str | Path) -> None:
    """Persist build artefacts to the ``work`` directory."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    dump_json(output_path / "out.ymmp", project)

    report = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "warning_count": len(warnings),
        "warnings": [warning.to_dict() for warning in warnings],
    }
    dump_json(output_path / "report.json", report)

    history_entry = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "events": [
            {
                "row": warning.row_index,
                "type": "warning",
                "message": warning.message,
            }
            for warning in warnings
        ],
    }
    with open(output_path / "history.jsonl", "a", encoding="utf-8") as fh:
        fh.write(dump_line(history_entry) + "\n")


def dump_line(entry: Dict[str, Any]) -> str:
    """Serialise a dictionary into a JSON string with UTF-8 characters preserved."""

    import json

    return json.dumps(entry, ensure_ascii=False)


def apply_hiragana_shrink(project_path: str | Path, output_path: str | Path, scale: float) -> None:
    """Apply hiragana shrink filter to a project JSON file."""

    import json

    project_path = Path(project_path)
    project = json.loads(project_path.read_text(encoding="utf-8"))

    for entry in project.get("timeline", []):
        telop = entry.get("telop")
        subtitle = entry.get("subtitle")
        if not telop:
            continue
        if not contains_hiragana(subtitle):
            continue
        telop["scale"] = round(float(telop.get("scale", 1.0)) * scale, 4)
    dump_json(output_path, project)
