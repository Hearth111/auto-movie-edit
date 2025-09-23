"""Generation of YMM4-compatible project structures."""

from __future__ import annotations
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
from datetime import datetime

from .models import TimelineRow, WorkbookData
from .utils import dump_json, contains_hiragana

class BuildWarning:
    """Represents a warning produced during project build."""
    def __init__(self, row_index: int | None, message: str) -> None:
        self.row_index, self.message = row_index, message
    def to_dict(self) -> dict[str, Any]: return {"row": self.row_index, "message": self.message}

class ProjectBuilder:
    """Transforms workbook data into a YMM4-compatible project by updating a scaffold."""

    def __init__(self, data: WorkbookData, fps: float = 60.0) -> None:
        self.data, self.warnings, self.fps = data, [], fps
        project_root = Path(__file__).resolve().parent.parent.parent
        self.scaffold_path = project_root / "scaffold.ymmp"
        self.characters_in_use: Set[str] = set()
        self.tachie_scaffold = {
            "$type": "YukkuriMovieMaker.Project.Items.TachieItem, YukkuriMovieMaker",
            "CharacterName": "キャラクター名",
            "TachieItemParameter": {"$type": "YukkuriMovieMaker.Plugin.Tachie.AnimationTachie.ItemParameter, YukkuriMovieMaker.Plugin.Tachie.AnimationTachie"},
            "X": 0.0, "Y": 150.0, "Zoom": 80.0, "Opacity": 100.0, "Rotation": 0.0,
            "Blend": "Normal", "Layer": 70, "Frame": 0, "Length": 300
        }
        self.part_map = {
            "目": "Eye", "口": "Mouth", "眉": "Eyebrow", "髪": "Hair", "体": "Body",
            "顔色": "Complexion", "他1": "Etc1", "他2": "Etc2", "他3": "Etc3"
        }

    def build(self) -> dict[str, Any]:
        """Builds the final YMM4 project by injecting items and characters into a scaffold file."""
        if not self.scaffold_path.exists(): raise FileNotFoundError(f"Scaffold file not found: '{self.scaffold_path}'")
        project = json.loads(self.scaffold_path.read_text("utf-8-sig"))
        
        # --- ★★★ ここが修正点 ★★★ ---
        # 1. Process all timeline items first to collect all necessary data, including characters in use.
        timeline_items = [item for row in self.data.timeline for item in self._build_row_items(row)]
        
        # 2. Now that self.characters_in_use is populated, create the definitions.
        # Also add any characters defined in the CHARACTERS sheet, even if not used on the timeline.
        for name in self.data.characters:
            self.characters_in_use.add(name)
        
        character_definitions = [{"Name": name, "Color": "#FFFFFFFF"} for name in self.characters_in_use]
        
        # 3. Inject everything into the project structure's two required locations.
        project["Characters"] = character_definitions
        if project.get("Timelines"):
            project["Timelines"][0]["Items"] = timeline_items
            project["Timelines"][0]["Characters"] = character_definitions
            
        return project

    def _build_row_items(self, row: TimelineRow) -> List[dict[str, Any]]:
        """Builds timeline items and collects character names used in the row."""
        items = []
        # Telop logic
        if row.telop and (pattern := self.data.telop_patterns.get(row.telop)):
            try:
                telop_item = self._create_item_from_template(pattern.overrides, row)
                telop_item["Text"] = row.subtitle
                if "Layer" not in telop_item: telop_item["Layer"] = 80
                items.append(telop_item)
            except Exception as e: self._warn(row, f"Telop build error for '{row.telop}': {e}")
        
        # Dynamic Tachie (from CHARACTERS sheet) logic
        if row.character and row.expressions and (char_def := self.data.characters.get(row.character)):
            try:
                self.characters_in_use.add(char_def.name) # Register character name
                tachie_item = self._create_item_from_template(self.tachie_scaffold, row)
                tachie_item["CharacterName"] = char_def.name
                params = tachie_item["TachieItemParameter"]
                for part_jp, expr_fn in row.expressions.items():
                    if (part_en := self.part_map.get(part_jp)) and (base_path := char_def.parts.get(part_jp)):
                        params[part_en] = str((Path(base_path) / f"{expr_fn}.png").resolve())
                if layer := self.data.layers.get("立ち絵"): tachie_item["Layer"] = layer.layer
                items.append(tachie_item)
            except Exception as e: self._warn(row, f"Dynamic Tachie build error: {e}")
        
        # Static Asset (including pre-absorbed Tachie) logic
        for obj in row.objects:
            if asset := self.data.assets.get(obj.identifier):
                try:
                    asset_item = self._create_item_from_template(asset.parameters, row)
                    # If this asset is a Tachie, find its character name and register it
                    if asset.kind == "tachie" and (char_name := asset_item.get("CharacterName")):
                        self.characters_in_use.add(char_name)
                    
                    if obj.layer is not None: asset_item["Layer"] = obj.layer
                    elif asset.default_layer is not None: asset_item["Layer"] = asset.default_layer
                    elif "Layer" not in asset_item: asset_item["Layer"] = 70
                    items.append(asset_item)
                except Exception as e: self._warn(row, f"Asset build error for '{obj.identifier}': {e}")
            else: self._warn(row, f"Asset not found: {obj.identifier}")
            
        return items

    def _create_item_from_template(self, template: dict, row: TimelineRow) -> dict:
        if not isinstance(template, dict): raise TypeError("Template data must be a dictionary.")
        item = json.loads(json.dumps(template))
        if row.start: item["Frame"] = int(row.start.to_seconds() * self.fps)
        if row.start and row.end: item["Length"] = int(max(0, row.end.to_seconds() - row.start.to_seconds()) * self.fps)
        return item

    def _warn(self, row: TimelineRow, message: str): self.warnings.append(BuildWarning(row.index, message))

def build_project(data: WorkbookData) -> Tuple[dict, List]:
    builder = ProjectBuilder(data)
    return builder.build(), builder.warnings

def write_outputs(project: dict, warnings: List, output_dir: str | Path):
    output_path = Path(output_dir); output_path.mkdir(parents=True, exist_ok=True)
    project["FilePath"] = str((output_path / "out.ymmp").resolve())
    dump_json(output_path / "out.ymmp", project)
    report = {"generated_at": datetime.utcnow().isoformat("T") + "Z", "warnings": [w.to_dict() for w in warnings]}
    dump_json(output_path / "report.json", report)

def apply_hiragana_shrink(project_path: str | Path, output_path: str | Path, scale: float):
    project = json.loads(Path(project_path).read_text("utf-8-sig"))
    for timeline in project.get("Timelines", []):
        for item in timeline.get("Items", []):
            if "TextItem" in item.get("$type", "") and contains_hiragana(item.get("Text")):
                if "Zoom" in item and "Values" in item["Zoom"]:
                    item["Zoom"]["Values"] = [{"Value": round(float(z.get("Value", 100.0)) * scale, 4)} for z in item["Zoom"]["Values"]]
    dump_json(output_path, project)