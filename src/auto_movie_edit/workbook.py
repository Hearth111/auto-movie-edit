"""Functions for reading and writing workbook files used by the pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from openpyxl import Workbook, load_workbook

from .models import (
    Asset,
    Character,
    FxPreset,
    LayerBand,
    Pack,
    TelopPattern,
    TimelineFx,
    TimelineObject,
    TimelineRow,
    WorkbookData,
)
from .utils import ensure_list, iter_nonempty, parse_mapping, parse_timecode


TELP_HEADERS = [
    "パターンID", "参照ソース", "上書きキー", "基準幅", "基準高さ",
    "FPS", "説明", "備考",
]
ASSET_HEADERS = [
    "素材ID", "種別", "パス", "既定レイヤ", "既定X",
    "既定Y", "既定ズーム", "備考",
]
PACK_HEADERS = [
    "パックID", "参照ソース", "上書きキー", "基準幅", "基準高さ",
    "FPS", "備考",
]
LAYER_HEADERS = ["役割", "レイヤ帯"]
FX_HEADERS = ["FX_ID", "種類", "パック", "アセット", "パラメータ"]
TIMELINE_HEADERS = [
    "開始", "終了", "字幕テキスト", "テロップ", "キャラクター", "表情(3つ内包)",
    "表情", "他1", "パック", "オブジェクト1", "オブジェクト2", "オブジェクト3",
    "背景", "FX_PARAM", "承認", "メモ",
]
SCHEMA_HEADERS = ["シート", "日本語", "キー"]
CHARACTERS_HEADERS = ["キャラクター名", "パーツ名", "ベースパス"]


@dataclass(slots=True)
class WorkbookTemplate:
    telp_headers: List[str]; asset_headers: List[str]; pack_headers: List[str]
    layer_headers: List[str]; fx_headers: List[str]; timeline_headers: List[str]
    schema_headers: List[str]; characters_headers: List[str]

DEFAULT_TEMPLATE = WorkbookTemplate(
    telp_headers=TELP_HEADERS, asset_headers=ASSET_HEADERS, pack_headers=PACK_HEADERS,
    layer_headers=LAYER_HEADERS, fx_headers=FX_HEADERS, timeline_headers=TIMELINE_HEADERS,
    schema_headers=SCHEMA_HEADERS, characters_headers=CHARACTERS_HEADERS,
)


def _write_headers(sheet, headers: Iterable[str]) -> None:
    for col, header in enumerate(headers, start=1):
        sheet.cell(row=1, column=col, value=header)

def create_workbook_template(template: WorkbookTemplate = DEFAULT_TEMPLATE) -> Workbook:
    wb = Workbook(); wb.remove(wb.active)
    _write_headers(wb.create_sheet("TELP_PATTERNS"), template.telp_headers)
    _write_headers(wb.create_sheet("ASSETS_SINGLE"), template.asset_headers)
    _write_headers(wb.create_sheet("PACKS_MULTI"), template.pack_headers)
    _write_headers(wb.create_sheet("LAYERS"), template.layer_headers)
    _write_headers(wb.create_sheet("FX"), template.fx_headers)
    _write_headers(wb.create_sheet("TIMELINE"), template.timeline_headers)
    _write_headers(wb.create_sheet("SCHEMA_MAP"), template.schema_headers)
    _write_headers(wb.create_sheet("CHARACTERS"), template.characters_headers)
    return wb

def save_workbook(workbook: Workbook, path: str | Path) -> None:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)

def load_sheet_dictionaries(sheet) -> list[dict[str, Any]]:
    if not sheet or sheet.max_row < 1: return []
    headers = [(cell.value or "").strip() for cell in sheet[1]]
    return [
        {h: row[i] for i, h in enumerate(headers) if h}
        for row in sheet.iter_rows(min_row=2, values_only=True)
    ]

def load_workbook_data(path: str | Path) -> WorkbookData:
    path = Path(path).resolve()
    wb = load_workbook(path, data_only=True)
    data = WorkbookData()

    # Load all dictionaries first
    if "TELP_PATTERNS" in wb.sheetnames:
        for r in iter_nonempty(load_sheet_dictionaries(wb["TELP_PATTERNS"])):
            if id := str(r.get("パターンID") or "").strip():
                data.telop_patterns[id] = TelopPattern(
                    pattern_id=id,
                    source=_string_or_none(r.get("参照ソース")),
                    overrides=parse_mapping(r.get("上書きキー")),
                    base_width=_safe_int(r.get("基準幅")),
                    base_height=_safe_int(r.get("基準高さ")),
                    fps=_safe_float(r.get("FPS")),
                    description=_string_or_none(r.get("説明")),
                    notes=_string_or_none(r.get("備考")),
                )
    if "ASSETS_SINGLE" in wb.sheetnames:
        for r in iter_nonempty(load_sheet_dictionaries(wb["ASSETS_SINGLE"])):
            if id := str(r.get("素材ID") or "").strip():
                data.assets[id] = Asset(
                    asset_id=id,
                    kind=_string_or_none(r.get("種別")),
                    path=_string_or_none(r.get("パス")),
                    parameters=parse_mapping(r.get("パラメータ")) if "パラメータ" in r else {},
                    default_layer=_safe_int(r.get("既定レイヤ")),
                    default_x=_safe_float(r.get("既定X")),
                    default_y=_safe_float(r.get("既定Y")),
                    default_zoom=_safe_float(r.get("既定ズーム")),
                    notes=_string_or_none(r.get("備考")),
                )
    if "CHARACTERS" in wb.sheetnames:
        for r in iter_nonempty(load_sheet_dictionaries(wb["CHARACTERS"])):
            if (name := _string_or_none(r.get("キャラクター名"))) and (part := _string_or_none(r.get("パーツ名"))) and (bp := _string_or_none(r.get("ベースパス"))):
                if name not in data.characters: data.characters[name] = Character(name=name)
                data.characters[name].parts[part] = bp
    if "LAYERS" in wb.sheetnames:
        for r in iter_nonempty(load_sheet_dictionaries(wb["LAYERS"])):
            if (role := str(r.get("役割") or "").strip()) and (layer := _safe_int(r.get("レイヤ帯"))) is not None: data.layers[role] = LayerBand(role=role, layer=layer)
    if "PACKS_MULTI" in wb.sheetnames:
        for r in iter_nonempty(load_sheet_dictionaries(wb["PACKS_MULTI"])):
            if id := str(r.get("パックID") or "").strip():
                data.packs[id] = Pack(
                    pack_id=id,
                    source=_string_or_none(r.get("参照ソース")),
                    overrides=parse_mapping(r.get("上書きキー")),
                    base_width=_safe_int(r.get("基準幅")),
                    base_height=_safe_int(r.get("基準高さ")),
                    fps=_safe_float(r.get("FPS")),
                    notes=_string_or_none(r.get("備考")),
                )
    if "FX" in wb.sheetnames:
        for r in iter_nonempty(load_sheet_dictionaries(wb["FX"])):
            if id := str(r.get("FX_ID") or "").strip():
                data.fx_presets[id] = FxPreset(
                    fx_id=id,
                    fx_type=_string_or_none(r.get("種類")),
                    source=_string_or_none(r.get("パック")),
                    asset=_string_or_none(r.get("アセット")),
                    parameters=parse_mapping(r.get("パラメータ")),
                )

    # Resolve template paths for telops and assets
    for p in data.telop_patterns.values():
        _resolve_template_path(p, path)
    for a in data.assets.values():
        _resolve_template_path(a, path, "path", "parameters")
    for pack in data.packs.values():
        _resolve_template_path(pack, path)

    # Timeline
    if "TIMELINE" in wb.sheetnames:
        records = load_sheet_dictionaries(wb["TIMELINE"])
        if records:
            keys = records[0].keys()
            obj_cols = [k for k in keys if k and (k.startswith("オブジェクト") or k == "背景")]
            expr_cols = {"表情(3つ内包)": ["目", "口", "眉"], "表情": ["顔色"], "他1": ["他1"]}
            fx_cols = [k for k in keys if k and k.startswith("FX") and k != "FX_PARAM"]
            for i, r in enumerate(iter_nonempty(records), 1):
                expr = {
                    part: filename
                    for column, parts in expr_cols.items()
                    if (filename := _string_or_none(r.get(column)))
                    for part in parts
                }
                objs = [
                    TimelineObject(
                        role=column,
                        identifier=identifier,
                        layer=data.layers.get(column).layer if data.layers.get(column) else None,
                    )
                    for column in obj_cols
                    if (identifier := _string_or_none(r.get(column)))
                ]
                packs = [
                    _normalize_identifier(value)
                    for value in ensure_list(r.get("パック"))
                    if _normalize_identifier(value)
                ]
                fx_values = {
                    column: [
                        _normalize_identifier(value)
                        for value in ensure_list(r.get(column))
                        if _normalize_identifier(value)
                    ]
                    for column in fx_cols
                }
                total_fx = sum(len(values) for values in fx_values.values())
                fx_param_raw = _parse_fx_params(r.get("FX_PARAM"))
                fxs: List[TimelineFx] = []
                for column_index, column in enumerate(fx_cols):
                    values = fx_values.get(column, [])
                    for fx_id in values:
                        params = _select_fx_parameters(fx_param_raw, fx_id, column, total_fx)
                        fxs.append(
                            TimelineFx(
                                fx_id=fx_id,
                                parameters=params,
                                source_column=column,
                                column_index=column_index,
                            )
                        )
                notes: Dict[str, Any] = {}
                if fx_param_raw not in (None, {}):
                    notes["fx_params"] = fx_param_raw
                if approval := _string_or_none(r.get("承認")):
                    notes["approval"] = approval
                if memo := _string_or_none(r.get("メモ")):
                    notes["memo"] = memo

                data.timeline.append(
                    TimelineRow(
                        index=i,
                        start=parse_timecode(_string_or_none(r.get("開始"))),
                        end=parse_timecode(_string_or_none(r.get("終了"))),
                        subtitle=_string_or_none(r.get("字幕テキスト")),
                        telop=_string_or_none(r.get("テロップ")),
                        character=_string_or_none(r.get("キャラクター")),
                        expressions=expr,
                        objects=objs,
                        fxs=fxs,
                        packs=packs,
                        notes=notes,
                    )
                )
    return data

def _resolve_template_path(item: TelopPattern | Asset | Pack, wb_path: Path, path_field="source", param_field="overrides"):
    source_path_str = getattr(item, path_field)
    if source_path_str and Path(source_path_str).suffix == ".json":
        source_path = Path(source_path_str)
        if not source_path.is_absolute():
            source_path = wb_path.parent / source_path
        if source_path.exists():
            try:
                setattr(item, param_field, json.loads(source_path.read_text(encoding="utf-8-sig")))
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Failed to load template {source_path}: {e}")
        else:
            print(f"Warning: Template file not found: {source_path}")


def _safe_int(v):
    return int(v) if v is not None and v != "" else None


def _safe_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _string_or_none(v):
    if v is None or v == "":
        return None
    return str(v).strip()


def _normalize_identifier(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    text = str(value).strip()
    return text or None


def _parse_fx_params(raw: Any) -> Any:
    if raw in (None, ""):
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            mapping = parse_mapping(text)
            return mapping if mapping else text
    return raw


def _normalize_param_value(value: Any) -> Dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = parse_mapping(value)
        return parsed if parsed else {"value": value}
    if isinstance(value, list):
        return {str(i): v for i, v in enumerate(value)}
    return {"value": value}


def _select_fx_parameters(raw: Any, fx_id: str, column_name: str, total_fx: int) -> Dict[str, Any]:
    if raw in (None, ""):
        return {}
    if isinstance(raw, dict):
        for key in (fx_id, column_name):
            if key in raw:
                return _normalize_param_value(raw[key])
        if total_fx == 1:
            return _normalize_param_value(raw)
        return {}
    if isinstance(raw, list):
        if total_fx == 1 and raw:
            return _normalize_param_value(raw[0])
        return {}
    if isinstance(raw, str):
        parsed = parse_mapping(raw)
        if parsed:
            if total_fx == 1:
                return parsed
            for key in (fx_id, column_name):
                if key in parsed:
                    return _normalize_param_value(parsed[key])
        return {"value": raw} if total_fx == 1 else {}
    return {"value": raw} if total_fx == 1 else {}
