"""Generation of YMM4-compatible project structures."""

from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, NamedTuple, Set, Tuple
from datetime import datetime

from .language import LanguageAnalyzer
from .models import (
    ExpressionPreset,
    FxPreset,
    Pack,
    TimelineFx,
    TimelineObject,
    TimelineRow,
    WorkbookData,
)
from .proposals import update_proposal_model
from .utils import dump_json, contains_hiragana, count_hiragana, ensure_list


_SCAFFOLD_CACHE: Dict[Path, tuple[float, int, dict[str, Any]]] = {}

_TACHIE_ALLOWED_EXTENSIONS: tuple[str, ...] = (".png", ".webp", ".jpg", ".jpeg", ".avif")
_TACHIE_FALLBACK_NAMES: tuple[str, ...] = ("default", "base", "normal", "通常", "ノーマル")


class TachieExpressionResolution(NamedTuple):
    path: Path | None
    used_fallback: bool
    attempts: Tuple[Path, ...]


def _loose_resolve(path: Path) -> Path:
    expanded = path.expanduser()
    try:
        return expanded.resolve(strict=False)
    except FileNotFoundError:
        return expanded


def _resolve_tachie_expression_path(base_path: str, expression: str) -> TachieExpressionResolution:
    expression = expression.strip()
    if not expression:
        return TachieExpressionResolution(None, False, tuple())

    placeholders = {"expression": expression, "expr": expression, "name": expression}
    formatted_path = base_path
    try:
        formatted_path = base_path.format(**placeholders)
    except (KeyError, ValueError):
        formatted_path = base_path

    candidate_strings = []
    for candidate in (formatted_path, base_path):
        if candidate and candidate not in candidate_strings:
            candidate_strings.append(candidate)

    attempt_entries: List[tuple[Path, bool]] = []
    search_roots: List[Path] = []
    seen_roots: set[Path] = set()

    for candidate_str in candidate_strings:
        base_candidate = _loose_resolve(Path(candidate_str))
        if base_candidate.is_file():
            return TachieExpressionResolution(base_candidate, False, (base_candidate,))
        if base_candidate.suffix and not base_candidate.is_dir():
            attempt_entries.append((base_candidate, False))
            parent = base_candidate.parent
            if parent not in seen_roots:
                search_roots.append(parent)
                seen_roots.add(parent)
        else:
            if base_candidate not in seen_roots:
                search_roots.append(base_candidate)
                seen_roots.add(base_candidate)

    def _expression_variants(expr: str) -> List[str]:
        variants = [expr]
        if "." not in expr:
            lowered = expr.lower()
            if lowered not in variants:
                variants.append(lowered)
            normalized = expr.replace(" ", "_")
            if normalized not in variants:
                variants.append(normalized)
        return variants

    variants = _expression_variants(expression)
    for root in search_roots:
        if root.is_file():
            attempt_entries.append((root, False))
            continue
        for variant in variants:
            variant_path = Path(variant)
            if variant_path.suffix:
                candidate = _loose_resolve(root / variant_path)
                attempt_entries.append((candidate, False))
            else:
                for ext in _TACHIE_ALLOWED_EXTENSIONS:
                    candidate = _loose_resolve(root / f"{variant}{ext}")
                    attempt_entries.append((candidate, False))
        for fallback_name in _TACHIE_FALLBACK_NAMES:
            fallback_variant = Path(fallback_name)
            if fallback_variant.suffix:
                candidate = _loose_resolve(root / fallback_variant)
                attempt_entries.append((candidate, True))
            else:
                for ext in _TACHIE_ALLOWED_EXTENSIONS:
                    candidate = _loose_resolve(root / f"{fallback_name}{ext}")
                    attempt_entries.append((candidate, True))

    attempts: List[Path] = []
    for candidate, is_fallback in attempt_entries:
        attempts.append(candidate)
        if candidate.exists():
            return TachieExpressionResolution(candidate, is_fallback, tuple(attempts))

    return TachieExpressionResolution(None, False, tuple(attempts))


def _load_scaffold_project(scaffold_path: Path) -> dict[str, Any]:
    resolved = scaffold_path.resolve()
    stat = resolved.stat()
    cached = _SCAFFOLD_CACHE.get(resolved)
    if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
        return copy.deepcopy(cached[2])
    project = json.loads(resolved.read_text("utf-8-sig"))
    _SCAFFOLD_CACHE[resolved] = (stat.st_mtime, stat.st_size, project)
    return copy.deepcopy(project)

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
        self.band_width = 10
        self.history_entries: List[Dict[str, Any]] = []
        self.language_analyzer = LanguageAnalyzer()
        self.expression_presets_by_tone: Dict[str, List[ExpressionPreset]] = {}
        self.default_expression_presets: List[ExpressionPreset] = []
        self._template_cache: Dict[tuple[str, Any], tuple[Mapping[str, Any], Tuple[tuple[str, Any], ...]]] = {}
        for preset in self.data.expression_presets.values():
            if not preset.tones:
                self.default_expression_presets.append(preset)
                continue
            for tone in preset.tones:
                normalized = self._normalize_tone(tone)
                if not normalized:
                    continue
                self.expression_presets_by_tone.setdefault(normalized, []).append(preset)
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
        self._tachie_last_paths: Dict[tuple[str, str], str] = {}

    def build(self) -> dict[str, Any]:
        """Builds the final YMM4 project by injecting items and characters into a scaffold file."""
        if not self.scaffold_path.exists(): raise FileNotFoundError(f"Scaffold file not found: '{self.scaffold_path}'")
        project = _load_scaffold_project(self.scaffold_path)

        timeline_items: List[dict[str, Any]] = []
        for row in self.data.timeline:
            timeline_items.extend(self._build_row_items(row))

        for name in self.data.characters:
            self.characters_in_use.add(name)

        character_definitions = [{"Name": name, "Color": "#FFFFFFFF"} for name in self.characters_in_use]

        # 3. Inject everything into the project structure's two required locations.
        project["Characters"] = character_definitions
        if project.get("Timelines"):
            project["Timelines"][0]["Items"] = timeline_items
            project["Timelines"][0]["Characters"] = character_definitions
            
        return project

    @staticmethod
    def _normalize_tone(value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        lowered = text.lower()
        if lowered in {"default", "auto"}:
            return None
        return text

    def _resolve_tone_hints(self, notes: Dict[str, Any]) -> tuple[bool, List[str]]:
        disable_auto = False
        tone_hints: List[str] = []
        for candidate in ensure_list(notes.get("expression_tones")):
            text = str(candidate).strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered in {"off", "none", "disable"} or text in {"オフ", "無効", "なし"}:
                disable_auto = True
                continue
            tone_hints.append(text)
        return disable_auto, tone_hints

    def _select_preset_for_tone(self, tone: str | None, character: str | None) -> ExpressionPreset | None:
        candidates = (
            self.default_expression_presets
            if tone is None
            else self.expression_presets_by_tone.get(tone, [])
        )
        if not candidates:
            return None
        for preset in candidates:
            if preset.character and preset.character == character:
                return preset
        for preset in candidates:
            if not preset.character:
                return preset
        return None

    def _apply_preset_parts(self, preset: ExpressionPreset, row: TimelineRow) -> bool:
        changed = False
        for part, value in preset.parts.items():
            if not value:
                continue
            if part not in row.expressions:
                row.expressions[part] = value
                changed = True
        return changed

    def _apply_expression_presets(self, row: TimelineRow) -> None:
        if not row.character:
            return
        if row.expressions is None:
            row.expressions = {}
        if row.notes is None:
            row.notes = {}
        notes = row.notes
        for preset_id in ensure_list(notes.get("expression_presets")):
            preset = self.data.expression_presets.get(str(preset_id))
            if not preset:
                continue
            if preset.character and preset.character != row.character:
                continue
            self._apply_preset_parts(preset, row)

        disable_auto, tone_hints = self._resolve_tone_hints(notes)
        if disable_auto:
            return

        tone_candidates: List[str] = []
        for tone_hint in tone_hints:
            normalized = self._normalize_tone(tone_hint)
            if normalized and normalized not in tone_candidates:
                tone_candidates.append(normalized)

        detected = self.language_analyzer.detect_tone(row.subtitle)
        normalized_detected = self._normalize_tone(detected)
        if normalized_detected and normalized_detected not in tone_candidates:
            tone_candidates.append(normalized_detected)

        for tone in tone_candidates:
            preset = self._select_preset_for_tone(tone, row.character)
            if preset and self._apply_preset_parts(preset, row):
                return

        default_preset = self._select_preset_for_tone(None, row.character)
        if default_preset:
            self._apply_preset_parts(default_preset, row)

    def _build_row_items(self, row: TimelineRow) -> List[dict[str, Any]]:
        """Builds timeline items and collects character names used in the row."""
        placements: List[dict[str, Any]] = []
        order_counter = 0

        self._apply_expression_presets(row)

        def register(items: List[dict[str, Any]], role: str | None, order: float, band: int | None = None) -> None:
            if not items:
                return
            inferred_band = band if band is not None else self._infer_layer_band(role)
            for offset, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                placements.append(
                    {
                        "item": item,
                        "band": inferred_band,
                        "order": order + offset * 0.01,
                        "explicit": "Layer" in item,
                        "role": role,
                        "row": row,
                    }
                )
                self._register_characters_from_item(item)
                self._warn_unresolved_filepaths(row, role, item)

        # Telop logic
        if row.telop:
            pattern = self.data.telop_patterns.get(row.telop)
            if not pattern:
                self._warn(row, f"Telop pattern not found: {row.telop}")
            else:
                try:
                    telop_item = self._create_item_from_template(pattern.overrides, row)
                    if row.subtitle and "Text" not in telop_item:
                        telop_item["Text"] = row.subtitle
                    elif row.subtitle:
                        telop_item["Text"] = row.subtitle
                    register([telop_item], "テロップ", order_counter, self._infer_layer_band("テロップ"))
                except Exception as exc:  # pragma: no cover - defensive path
                    self._warn(row, f"Telop build error for '{row.telop}': {exc}")
            order_counter += 1

        # Dynamic Tachie logic
        if row.character:
            char_def = self.data.characters.get(row.character)
            if not char_def:
                self._warn(row, f"Character not found: {row.character}")
            elif not row.expressions:
                self._warn(row, f"No expressions provided for character '{row.character}'")
            else:
                try:
                    self.characters_in_use.add(char_def.name)
                    tachie_item = self._create_item_from_template(self.tachie_scaffold, row)
                    tachie_item["CharacterName"] = char_def.name
                    params = tachie_item.setdefault("TachieItemParameter", {})
                    for part_jp, expr_fn in row.expressions.items():
                        part_en = self.part_map.get(part_jp)
                        base_path = char_def.parts.get(part_jp) if char_def else None
                        key = (char_def.name, part_en) if part_en else None
                        if part_en and base_path:
                            resolution = _resolve_tachie_expression_path(base_path, expr_fn)
                            if resolution.path:
                                params[part_en] = str(resolution.path)
                                if key:
                                    self._tachie_last_paths[key] = str(resolution.path)
                                if resolution.used_fallback:
                                    self._warn(
                                        row,
                                        f"Tachie expression '{expr_fn}' missing for part '{part_jp}'. Fallback to '{resolution.path.name}'",
                                    )
                            else:
                                reused = key and self._tachie_last_paths.get(key)
                                if reused:
                                    params[part_en] = reused
                                    self._warn(
                                        row,
                                        f"Tachie expression '{expr_fn}' missing for part '{part_jp}'. Reusing previous '{Path(reused).name}'",
                                    )
                                else:
                                    attempted_names = [p.name for p in resolution.attempts if p and p.name]
                                    attempts = ", ".join(dict.fromkeys(attempted_names[-5:])) if attempted_names else ""
                                    detail = f" Tried: {attempts}" if attempts else ""
                                    self._warn(
                                        row,
                                        f"Tachie expression file not found for part '{part_jp}' of '{char_def.name}' (expr '{expr_fn}').{detail}",
                                    )
                        elif not part_en:
                            self._warn(row, f"Unknown tachie part: {part_jp}")
                        else:
                            self._warn(row, f"Tachie base path missing for part '{part_jp}' of character '{char_def.name}'")
                    register([tachie_item], "立ち絵", order_counter, self._infer_layer_band("立ち絵"))
                except Exception as exc:  # pragma: no cover - defensive path
                    self._warn(row, f"Dynamic Tachie build error: {exc}")
            order_counter += 1

        # Packs applied on the row
        for pack_id in row.packs:
            if pack := self.data.packs.get(pack_id):
                pack_items = self._instantiate_pack(pack, row)
                register(pack_items, "パック", order_counter, self._infer_layer_band("パック"))
            else:
                self._warn(row, f"Pack not found: {pack_id}")
            order_counter += 1

        # Static assets and direct objects
        for obj_index, obj in enumerate(row.objects):
            placements_for_object = self._instantiate_object(obj, row)
            base_band = obj.layer if obj.layer is not None else self._infer_layer_band(obj.role)
            register(placements_for_object, obj.role, order_counter, base_band)
            order_counter += 1

        # FX presets
        for fx in row.fxs:
            fx_items = self._instantiate_fx(fx, row)
            band_reference = fx.source_key or fx.source_column or fx.fx_id
            fx_band = self._infer_layer_band(band_reference)
            register(fx_items, band_reference, order_counter, fx_band)
            order_counter += 1

        self._finalize_layers(placements)
        self._record_history(row, placements)
        return [p["item"] for p in placements]

    def _create_item_from_template(self, template: dict | list | None, row: TimelineRow) -> dict:
        resolved_template = self._resolve_template_dict(template)
        item = self._clone_template(resolved_template)
        if row.start:
            frame_value = int(row.start.to_seconds() * self.fps)
            item["Frame"] = frame_value
        if row.start and row.end:
            start_seconds = row.start.to_seconds()
            end_seconds = row.end.to_seconds()
            length_seconds = max(0.0, end_seconds - start_seconds)
            item["Length"] = int(length_seconds * self.fps)
        return item

    def _instantiate_object(self, obj: TimelineObject, row: TimelineRow) -> List[dict[str, Any]]:
        items: List[dict[str, Any]] = []
        asset = self.data.assets.get(obj.identifier)
        if not asset:
            self._warn(row, f"Asset not found: {obj.identifier}")
            return items
        obj.resolved = asset
        if not asset.parameters:
            self._warn(row, f"Asset '{asset.asset_id}' has no template parameters")
            return items
        templates = asset.parameters if isinstance(asset.parameters, list) else [asset.parameters]
        for template in templates:
            try:
                item = self._create_item_from_template(template, row)
            except Exception as exc:  # pragma: no cover - defensive path
                self._warn(row, f"Asset build error for '{obj.identifier}': {exc}")
                continue
            if asset.path and "FilePath" not in item:
                item["FilePath"] = asset.path
            if asset.default_x is not None:
                item.setdefault("X", asset.default_x)
            if asset.default_y is not None:
                item.setdefault("Y", asset.default_y)
            if asset.default_zoom is not None:
                item.setdefault("Zoom", asset.default_zoom)
            if obj.layer is not None:
                item.setdefault("Layer", obj.layer)
            elif asset.default_layer is not None:
                item.setdefault("Layer", asset.default_layer)
            if asset.kind == "tachie" and (char_name := item.get("CharacterName")):
                self.characters_in_use.add(char_name)
            items.append(item)
        return items

    def _instantiate_pack(self, pack: Pack, row: TimelineRow) -> List[dict[str, Any]]:
        template = pack.overrides
        if template is None:
            self._warn(row, f"Pack '{pack.pack_id}' has no template data")
            return []
        if isinstance(template, dict):
            if "Items" in template and isinstance(template["Items"], list):
                source_items = template["Items"]
            elif "$type" in template:
                source_items = [template]
            else:
                source_items = []
        elif isinstance(template, list):
            source_items = template
        else:
            self._warn(row, f"Unsupported pack template format for '{pack.pack_id}'")
            return []
        if not source_items:
            self._warn(row, f"Pack '{pack.pack_id}' has no items")
            return []
        instantiated: List[dict[str, Any]] = []
        for base_item in source_items:
            try:
                item = self._create_item_from_template(base_item, row)
            except Exception as exc:  # pragma: no cover - defensive path
                self._warn(row, f"Pack '{pack.pack_id}' build error: {exc}")
                continue
            instantiated.append(item)
        return instantiated

    def _instantiate_fx(self, fx: TimelineFx, row: TimelineRow) -> List[dict[str, Any]]:
        preset = self.data.fx_presets.get(fx.fx_id)
        if not preset:
            self._warn(row, f"FX preset not found: {fx.fx_id}")
            return []
        fx.resolved = preset
        items: List[dict[str, Any]] = []
        if preset.source:
            pack = self.data.packs.get(preset.source)
            if pack:
                items.extend(self._instantiate_pack(pack, row))
            else:
                self._warn(row, f"FX preset '{fx.fx_id}' references missing pack '{preset.source}'")
        elif preset.asset:
            asset_items = self._instantiate_object(
                TimelineObject(role=preset.fx_type or "FX", identifier=preset.asset, layer=None, resolved=None),
                row,
            )
            if not asset_items:
                self._warn(row, f"FX preset '{fx.fx_id}' asset not resolved: {preset.asset}")
            items.extend(asset_items)
        else:
            self._warn(row, f"FX preset '{fx.fx_id}' has no source or asset")

        self._validate_fx_parameters(fx, preset, row)
        combined_params = self._deep_copy(preset.parameters) if preset.parameters else {}
        if fx.parameters:
            combined_params = self._merge_parameters(combined_params, fx.parameters)
        if combined_params:
            for item in items:
                self._apply_parameters(item, combined_params)
        fx.applied_parameters = combined_params if combined_params else {}
        return items

    def _validate_fx_parameters(self, fx: TimelineFx, preset: FxPreset, row: TimelineRow) -> None:
        if not fx.parameters:
            return
        if preset.parameters:
            expected = self._flatten_structure_keys(preset.parameters)
            provided = self._flatten_structure_keys(fx.parameters)
            unknown = provided - expected
            if unknown:
                self._warn(
                    row,
                    f"FX '{fx.fx_id}' overrides unknown parameter(s): {', '.join(sorted(unknown))}",
                )
        else:
            self._warn(row, f"FX '{fx.fx_id}' has no base parameters but overrides were provided")

    def _flatten_structure_keys(self, data: Any, prefix: str = "") -> Set[str]:
        keys: Set[str] = set()
        if isinstance(data, dict):
            for key, value in data.items():
                new_prefix = f"{prefix}.{key}" if prefix else str(key)
                keys.add(new_prefix)
                keys.update(self._flatten_structure_keys(value, new_prefix))
        elif isinstance(data, list):
            for index, value in enumerate(data):
                new_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
                keys.add(new_prefix)
                keys.update(self._flatten_structure_keys(value, new_prefix))
        return keys

    def _apply_parameters(self, target: dict[str, Any], overrides: Dict[str, Any]) -> None:
        for key, value in overrides.items():
            if isinstance(value, Mapping) and isinstance(target.get(key), Mapping):
                nested = dict(target[key])
                target[key] = nested
                self._apply_parameters(nested, value)
            elif isinstance(value, Mapping):
                target[key] = self._clone_parameter_value(value)
            else:
                target[key] = self._clone_parameter_value(value)

    def _merge_parameters(self, base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
        result = self._clone_parameter_value(base) if base else {}
        for key, value in overrides.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_parameters(result[key], value)
            else:
                result[key] = self._clone_parameter_value(value)
        return result

    def _finalize_layers(self, placements: List[dict[str, Any]]) -> None:
        bands: Dict[tuple[int, int], List[dict[str, Any]]] = {}
        for placement in placements:
            band = placement["band"]
            if band is None or placement["explicit"]:
                continue
            key = (placement["row"].index, int(band))
            bands.setdefault(key, []).append(placement)
        for (row_index, band), items in bands.items():
            items.sort(key=lambda p: p["order"])  # left -> right
            for offset, placement in enumerate(items):
                if offset >= self.band_width:
                    placement["item"]["Layer"] = band + self.band_width - 1
                    self._warn(placement["row"], f"Layer band overflow at band {band} for role '{placement['role']}'")
                else:
                    placement["item"]["Layer"] = band + (self.band_width - offset - 1)

    def _infer_layer_band(self, role: str | None) -> int:
        if role and (band := self.data.layers.get(role)):
            return band.layer
        if role:
            if role.startswith("オブジェクト"):
                return 60
            if role.startswith("FX"):
                return 50
            if role == "背景":
                return 10
        if role == "テロップ":
            return 80
        if role == "立ち絵":
            return 70
        if role == "パック":
            return 60
        return 50

    def _register_characters_from_item(self, item: dict[str, Any]) -> None:
        char_name = item.get("CharacterName")
        if isinstance(char_name, str):
            self.characters_in_use.add(char_name)

    def _warn_unresolved_filepaths(self, row: TimelineRow, role: str | None, item: dict[str, Any]) -> None:
        file_path = item.get("FilePath")
        if isinstance(file_path, str) and file_path.startswith("template://"):
            context = f" for role '{role}'" if role else ""
            self._warn(row, f"Unresolved template path{context}: {file_path}")

    def _resolve_template_dict(self, template: dict | list | None) -> Mapping[str, Any]:
        if template is None:
            raise TypeError("Template data is missing.")
        if isinstance(template, Sequence) and not isinstance(template, (str, bytes, bytearray, Mapping)):
            if not template:
                raise ValueError("Template list is empty.")
            first = template[0]
            if not isinstance(first, Mapping):
                raise TypeError("Template data must be a dictionary.")
            return first
        if not isinstance(template, Mapping):
            raise TypeError("Template data must be a dictionary.")
        return template

    def _digest_template(self, template: Mapping[str, Any]) -> str | None:
        try:
            serialized = json.dumps(template, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            return None
        return hashlib.sha1(serialized.encode("utf-8")).hexdigest()

    def _clone_template(self, template: Mapping[str, Any]) -> dict[str, Any]:
        identity_key = ("id", id(template))
        cached = self._template_cache.get(identity_key)
        if not cached or cached[0] is not template:
            digest = self._digest_template(template)
            digest_key = ("digest", digest) if digest else None
            if digest_key:
                cached = self._template_cache.get(digest_key)
            items = cached[1] if cached else tuple(template.items())
            cached = (template, items)
            self._template_cache[identity_key] = cached
            if digest_key:
                self._template_cache[digest_key] = cached
        _, items = cached
        cloned: dict[str, Any] = {}
        for key, value in items:
            if isinstance(value, Mapping):
                cloned[key] = dict(value)
            elif isinstance(value, list):
                cloned[key] = list(value)
            else:
                cloned[key] = value
        return cloned

    def _clone_parameter_value(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {k: self._clone_parameter_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._clone_parameter_value(v) for v in value]
        return value

    def _deep_copy(self, data: Any) -> Any:
        return copy.deepcopy(data)

    def _warn(self, row: TimelineRow, message: str): self.warnings.append(BuildWarning(row.index, message))

    def _record_history(self, row: TimelineRow, placements: List[dict[str, Any]]) -> None:
        timestamp = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        history_entry: Dict[str, Any] = {
            "timestamp": timestamp,
            "row_index": row.index,
            "start": row.start.to_string() if row.start else None,
            "end": row.end.to_string() if row.end else None,
            "subtitle": row.subtitle,
            "telop": row.telop,
            "character": row.character,
            "expressions": dict(row.expressions),
            "packs": list(row.packs),
            "objects": [
                {
                    "role": obj.role,
                    "source_column": obj.source_column,
                    "identifier": obj.identifier,
                    "resolved_asset": obj.resolved.asset_id if obj.resolved else None,
                    "asset_path": obj.resolved.path if obj.resolved and obj.resolved.path else None,
                }
                for obj in row.objects
            ],
            "fx": [
                {
                    "fx_id": fx.fx_id,
                    "source_column": fx.source_column,
                    "source_key": fx.source_key,
                    "parameters": fx.parameters,
                    "applied_parameters": fx.applied_parameters,
                    "preset": {
                        "type": fx.resolved.fx_type if fx.resolved else None,
                        "source": fx.resolved.source if fx.resolved else None,
                        "asset": fx.resolved.asset if fx.resolved else None,
                    },
                }
                for fx in row.fxs
            ],
            "notes": dict(row.notes),
        }
        history_entry["generated_items"] = [
            {
                "role": placement.get("role"),
                "layer": placement.get("item", {}).get("Layer"),
                "type": placement.get("item", {}).get("$type"),
            }
            for placement in placements
        ]
        self.history_entries.append(history_entry)

def build_project(data: WorkbookData) -> Tuple[dict, List, List[Dict[str, Any]]]:
    builder = ProjectBuilder(data)
    project = builder.build()
    return project, builder.warnings, builder.history_entries

def write_outputs(project: dict, warnings: List, output_dir: str | Path, history: List[Dict[str, Any]] | None = None):
    output_path = Path(output_dir); output_path.mkdir(parents=True, exist_ok=True)
    project["FilePath"] = str((output_path / "out.ymmp").resolve())
    dump_json(output_path / "out.ymmp", project)
    report = {"generated_at": datetime.utcnow().isoformat("T") + "Z", "warnings": [w.to_dict() for w in warnings]}
    history_entries = history or []
    history_count = _write_history_entries(history_entries, warnings, output_path)
    model_path = update_proposal_model(history_entries, output_path)
    if history_count:
        report["history"] = {
            "count": history_count,
            "directory": str((output_path / "history").resolve()),
        }
    if model_path:
        report.setdefault("ai", {})["proposal_model"] = str(Path(model_path).resolve())
    dump_json(output_path / "report.json", report)

def _write_history_entries(history: List[Dict[str, Any]], warnings: List[BuildWarning], output_path: Path) -> int:
    if not history:
        return 0
    warning_map: Dict[int, List[str]] = {}
    for warning in warnings:
        if warning.row_index is None:
            continue
        warning_map.setdefault(warning.row_index, []).append(warning.message)

    enriched: List[Dict[str, Any]] = []
    for entry in history:
        row_index = entry.get("row_index")
        enriched_entry = dict(entry)
        if row_index in warning_map:
            enriched_entry["warnings"] = warning_map[row_index]
        enriched.append(enriched_entry)

    date_dir = output_path / "history" / datetime.utcnow().strftime("%Y%m%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    history_path = date_dir / "history.jsonl"
    with history_path.open("a", encoding="utf-8") as fh:
        for entry in enriched:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return len(enriched)


def _first_numeric_value(data: Any, default: float = 100.0) -> float:
    if isinstance(data, Mapping):
        values = data.get("Values")
        if isinstance(values, list):
            for entry in values:
                if isinstance(entry, Mapping):
                    candidate = entry.get("Value")
                    if isinstance(candidate, (int, float)):
                        return float(candidate)
        candidate = data.get("Value")
        if isinstance(candidate, (int, float)):
            return float(candidate)
    elif isinstance(data, list):
        for entry in data:
            if isinstance(entry, Mapping):
                candidate = entry.get("Value")
                if isinstance(candidate, (int, float)):
                    return float(candidate)
            elif isinstance(entry, (int, float)):
                return float(entry)
    return default


def _estimate_text_layout(item: Mapping[str, Any]) -> tuple[int, int, int]:
    text = str(item.get("Text", ""))
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        lines = [text.strip()] if text.strip() else [text]
    line_count = max(1, len(lines))
    longest_line = max((len(line) for line in lines), default=len(text))
    total_chars = sum(len(line) for line in lines) or len(text)
    return line_count, longest_line, total_chars


def _determine_hiragana_scale(item: Mapping[str, Any], base_scale: float) -> float:
    text = str(item.get("Text", ""))
    if not text.strip():
        return min(1.0, max(base_scale, 0.6))

    line_count, longest_line, total_chars = _estimate_text_layout(item)
    hira_count = count_hiragana(text)
    effective_chars = max(1, total_chars)
    hira_ratio = hira_count / effective_chars

    shrink_strength = math.pow(hira_ratio, 0.7)
    dynamic_scale = 1 - (1 - base_scale) * shrink_strength

    font_size = _first_numeric_value(item.get("FontSize"), default=100.0)
    base_zoom = _first_numeric_value(item.get("Zoom"), default=100.0)
    char_width = font_size * 0.62
    approx_width = char_width * max(1, longest_line) * (base_zoom / 100.0)
    target_width = 1080 * 0.9  # assume portrait 1080x1920 canvas
    if target_width > 0:
        width_ratio = approx_width / target_width
        if width_ratio > 1.0:
            dynamic_scale = min(dynamic_scale, 1.0 / width_ratio)
        else:
            slack = 1.0 - width_ratio
            if slack > 0.15:
                dynamic_scale = min(1.0, dynamic_scale + slack * 0.35)

    if line_count > 2:
        dynamic_scale *= 0.98 ** (line_count - 2)
    elif line_count == 1 and longest_line <= 6:
        dynamic_scale = min(1.0, dynamic_scale + 0.05)

    return max(0.55, min(dynamic_scale, 1.0))


def apply_hiragana_shrink(project_path: str | Path, output_path: str | Path, scale: float):
    project = json.loads(Path(project_path).read_text("utf-8-sig"))
    for timeline in project.get("Timelines", []):
        for item in timeline.get("Items", []):
            if "TextItem" in item.get("$type", "") and contains_hiragana(item.get("Text")):
                zoom_block = item.get("Zoom")
                if isinstance(zoom_block, Mapping):
                    values = zoom_block.get("Values")
                else:
                    values = None
                if isinstance(values, list) and values:
                    base_value = _first_numeric_value(values, default=100.0)
                    if base_value == 0:
                        base_value = 100.0
                    ratios: List[float] = []
                    for entry in values:
                        current = entry.get("Value") if isinstance(entry, Mapping) else None
                        current_value = float(current) if isinstance(current, (int, float)) else base_value
                        ratios.append(current_value / base_value if base_value else 1.0)
                    dynamic_scale = _determine_hiragana_scale(item, scale)
                    new_base = base_value * dynamic_scale
                    new_values: List[dict[str, Any]] = []
                    for entry, ratio in zip(values, ratios):
                        updated = dict(entry) if isinstance(entry, Mapping) else {"Value": entry}
                        updated["Value"] = round(new_base * ratio, 4)
                        new_values.append(updated)
                    zoom_block["Values"] = new_values
    dump_json(output_path, project)
