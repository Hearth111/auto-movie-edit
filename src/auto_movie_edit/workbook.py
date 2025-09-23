"""Functions for reading and writing workbook files used by the pipeline."""

from __future__ import annotations

import json
from collections import defaultdict
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
            if id := str(r.get("パターンID") or "").strip(): data.telop_patterns[id] = TelopPattern(pattern_id=id, source=r.get("参照ソース"), overrides=parse_mapping(r.get("上書きキー")), description=r.get("説明"), notes=r.get("備考"))
    if "ASSETS_SINGLE" in wb.sheetnames:
        for r in iter_nonempty(load_sheet_dictionaries(wb["ASSETS_SINGLE"])):
            if id := str(r.get("素材ID") or "").strip(): data.assets[id] = Asset(asset_id=id, kind=r.get("種別"), path=r.get("パス"), default_layer=_safe_int(r.get("既定レイヤ")), notes=r.get("備考"))
    if "CHARACTERS" in wb.sheetnames:
        for r in iter_nonempty(load_sheet_dictionaries(wb["CHARACTERS"])):
            if (name := _string_or_none(r.get("キャラクター名"))) and (part := _string_or_none(r.get("パーツ名"))) and (bp := _string_or_none(r.get("ベースパス"))):
                if name not in data.characters: data.characters[name] = Character(name=name)
                data.characters[name].parts[part] = bp
    if "LAYERS" in wb.sheetnames:
        for r in iter_nonempty(load_sheet_dictionaries(wb["LAYERS"])):
            if (role := str(r.get("役割") or "").strip()) and (layer := _safe_int(r.get("レイヤ帯"))) is not None: data.layers[role] = LayerBand(role=role, layer=layer)

    # Resolve template paths for telops and assets
    for p in data.telop_patterns.values(): _resolve_template_path(p, path)
    for a in data.assets.values(): _resolve_template_path(a, path, "path", "parameters")

    # Timeline
    if "TIMELINE" in wb.sheetnames:
        records = load_sheet_dictionaries(wb["TIMELINE"])
        if records:
            keys = records[0].keys()
            obj_cols = [k for k in keys if k and (k.startswith("オブジェクト") or k == "背景")]
            expr_cols = {"表情(3つ内包)": ["目", "口", "眉"], "表情": ["顔色"], "他1": ["他1"]}
            for i, r in enumerate(iter_nonempty(records), 1):
                expr = {p: fn for c, ps in expr_cols.items() if (fn := _string_or_none(r.get(c))) for p in ps}
                objs = [TimelineObject(role=c, identifier=id, layer=data.layers.get(c).layer if data.layers.get(c) else None) for c in obj_cols if (id := _string_or_none(r.get(c)))]
                data.timeline.append(TimelineRow(
                    index=i, start=parse_timecode(_string_or_none(r.get("開始"))), end=parse_timecode(_string_or_none(r.get("終了"))),
                    subtitle=_string_or_none(r.get("字幕テキスト")), telop=_string_or_none(r.get("テロップ")),
                    character=_string_or_none(r.get("キャラクター")), expressions=expr, objects=objs
                ))
    return data

def _resolve_template_path(item: TelopPattern | Asset, wb_path: Path, path_field="source", param_field="overrides"):
    source_path_str = getattr(item, path_field)
    if source_path_str and Path(source_path_str).suffix == ".json":
        source_path = Path(source_path_str)
        if not source_path.is_absolute(): source_path = wb_path.parent / source_path
        if source_path.exists():
            try: setattr(item, param_field, json.loads(source_path.read_text(encoding="utf-8-sig")))
            except (json.JSONDecodeError, IOError) as e: print(f"Warning: Failed to load template {source_path}: {e}")
        else: print(f"Warning: Template file not found: {source_path}")

def _safe_int(v): return int(v) if v is not None and v != "" else None
def _string_or_none(v): return str(v).strip() if v is not None and v != "" else None