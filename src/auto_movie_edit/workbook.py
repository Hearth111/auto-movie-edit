"""Functions for reading and writing workbook files used by the pipeline."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from openpyxl import Workbook, load_workbook

from .models import (
    Asset,
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
    "パターンID",
    "参照ソース",
    "上書きキー",
    "基準幅",
    "基準高さ",
    "FPS",
    "説明",
    "備考",
]

ASSET_HEADERS = [
    "素材ID",
    "種別",
    "パス",
    "既定レイヤ",
    "既定X",
    "既定Y",
    "既定ズーム",
    "備考",
]

PACK_HEADERS = [
    "パックID",
    "参照ソース",
    "上書きキー",
    "基準幅",
    "基準高さ",
    "FPS",
    "備考",
]

LAYER_HEADERS = [
    "役割",
    "レイヤ帯",
]

FX_HEADERS = [
    "FX_ID",
    "種類",
    "パック",
    "アセット",
    "パラメータ",
]

TIMELINE_HEADERS = [
    "開始",
    "終了",
    "字幕テキスト",
    "テロップ",
    "パック",
    "オブジェクト1",
    "オブジェクト2",
    "オブジェクト3",
    "背景",
    "FX_PARAM",
    "承認",
    "メモ",
]

SCHEMA_HEADERS = [
    "シート",
    "日本語",
    "キー",
]


@dataclass(slots=True)
class WorkbookTemplate:
    """Represents the workbook template structure."""

    telp_headers: List[str] = None
    asset_headers: List[str] = None
    pack_headers: List[str] = None
    layer_headers: List[str] = None
    fx_headers: List[str] = None
    timeline_headers: List[str] = None
    schema_headers: List[str] = None


DEFAULT_TEMPLATE = WorkbookTemplate(
    telp_headers=TELP_HEADERS,
    asset_headers=ASSET_HEADERS,
    pack_headers=PACK_HEADERS,
    layer_headers=LAYER_HEADERS,
    fx_headers=FX_HEADERS,
    timeline_headers=TIMELINE_HEADERS,
    schema_headers=SCHEMA_HEADERS,
)


def _write_headers(sheet, headers: Iterable[str]) -> None:
    for col, header in enumerate(headers, start=1):
        sheet.cell(row=1, column=col, value=header)


def create_workbook_template(template: WorkbookTemplate = DEFAULT_TEMPLATE) -> Workbook:
    """Create a workbook according to the template structure."""

    wb = Workbook()
    wb.remove(wb.active)

    telp_sheet = wb.create_sheet("TELP_PATTERNS")
    _write_headers(telp_sheet, template.telp_headers)

    asset_sheet = wb.create_sheet("ASSETS_SINGLE")
    _write_headers(asset_sheet, template.asset_headers)

    pack_sheet = wb.create_sheet("PACKS_MULTI")
    _write_headers(pack_sheet, template.pack_headers)

    layer_sheet = wb.create_sheet("LAYERS")
    _write_headers(layer_sheet, template.layer_headers)

    fx_sheet = wb.create_sheet("FX")
    _write_headers(fx_sheet, template.fx_headers)

    timeline_sheet = wb.create_sheet("TIMELINE")
    _write_headers(timeline_sheet, template.timeline_headers)

    schema_sheet = wb.create_sheet("SCHEMA_MAP")
    _write_headers(schema_sheet, template.schema_headers)

    return wb


def save_workbook(workbook: Workbook, path: str | Path) -> None:
    """Persist the provided workbook to disk."""

    path = Path(path)
    workbook.save(path)


def load_sheet_dictionaries(sheet) -> list[dict[str, Any]]:
    """Load a worksheet into a list of dictionaries keyed by header."""

    headers: list[str] = []
    for cell in sheet[1]:
        headers.append((cell.value or "").strip())
    rows: list[dict[str, Any]] = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        record = {}
        for index, header in enumerate(headers):
            if not header:
                continue
            record[header] = row[index]
        rows.append(record)
    return rows


def load_workbook_data(path: str | Path) -> WorkbookData:
    """Load workbook data into strongly typed models."""

    path = Path(path)
    wb = load_workbook(path, data_only=True)

    data = WorkbookData()

    if "TELP_PATTERNS" in wb.sheetnames:
        for record in iter_nonempty(load_sheet_dictionaries(wb["TELP_PATTERNS"])):
            pattern_id = str(record.get("パターンID") or "").strip()
            if not pattern_id:
                continue
            data.telop_patterns[pattern_id] = TelopPattern(
                pattern_id=pattern_id,
                source=record.get("参照ソース"),
                overrides=parse_mapping(record.get("上書きキー")),
                base_width=_safe_int(record.get("基準幅")),
                base_height=_safe_int(record.get("基準高さ")),
                fps=_safe_float(record.get("FPS")),
                description=record.get("説明"),
                notes=record.get("備考"),
            )

    if "ASSETS_SINGLE" in wb.sheetnames:
        for record in iter_nonempty(load_sheet_dictionaries(wb["ASSETS_SINGLE"])):
            asset_id = str(record.get("素材ID") or "").strip()
            if not asset_id:
                continue
            data.assets[asset_id] = Asset(
                asset_id=asset_id,
                kind=record.get("種別"),
                path=record.get("パス"),
                default_layer=_safe_int(record.get("既定レイヤ")),
                default_x=_safe_float(record.get("既定X")),
                default_y=_safe_float(record.get("既定Y")),
                default_zoom=_safe_float(record.get("既定ズーム")),
                notes=record.get("備考"),
            )

    if "PACKS_MULTI" in wb.sheetnames:
        for record in iter_nonempty(load_sheet_dictionaries(wb["PACKS_MULTI"])):
            pack_id = str(record.get("パックID") or "").strip()
            if not pack_id:
                continue
            data.packs[pack_id] = Pack(
                pack_id=pack_id,
                source=record.get("参照ソース"),
                overrides=parse_mapping(record.get("上書きキー")),
                base_width=_safe_int(record.get("基準幅")),
                base_height=_safe_int(record.get("基準高さ")),
                fps=_safe_float(record.get("FPS")),
                notes=record.get("備考"),
            )

    if "LAYERS" in wb.sheetnames:
        for record in iter_nonempty(load_sheet_dictionaries(wb["LAYERS"])):
            role = str(record.get("役割") or "").strip()
            if not role:
                continue
            layer_value = _safe_int(record.get("レイヤ帯"))
            if layer_value is None:
                continue
            data.layers[role] = LayerBand(role=role, layer=layer_value)

    if "FX" in wb.sheetnames:
        for record in iter_nonempty(load_sheet_dictionaries(wb["FX"])):
            fx_id = str(record.get("FX_ID") or "").strip()
            if not fx_id:
                continue
            data.fx_presets[fx_id] = FxPreset(
                fx_id=fx_id,
                fx_type=record.get("種類"),
                source=record.get("パック"),
                asset=record.get("アセット"),
                parameters=parse_mapping(record.get("パラメータ")),
            )

    if "SCHEMA_MAP" in wb.sheetnames:
        schema_records = load_sheet_dictionaries(wb["SCHEMA_MAP"])
        grouped: Dict[str, Dict[str, str]] = defaultdict(dict)
        for record in iter_nonempty(schema_records):
            sheet_name = str(record.get("シート") or "").strip()
            if not sheet_name:
                continue
            japanese = str(record.get("日本語") or "").strip()
            key = str(record.get("キー") or "").strip()
            if japanese and key:
                grouped[sheet_name][japanese] = key
        data.schema_map = dict(grouped)

    if "TIMELINE" in wb.sheetnames:
        timeline_records = load_sheet_dictionaries(wb["TIMELINE"])
        fx_param_key = "FX_PARAM"
        fx_columns = [header for header in timeline_records[0].keys() if header.startswith("FX_")] if timeline_records else []
        object_columns = [
            header
            for header in timeline_records[0].keys()
            if header.startswith("オブジェクト") or header == "背景"
        ] if timeline_records else []

        for index, record in enumerate(iter_nonempty(timeline_records), start=1):
            start = parse_timecode(_string_or_none(record.get("開始")))
            end = parse_timecode(_string_or_none(record.get("終了")))
            subtitle = _string_or_none(record.get("字幕テキスト"))
            telop = _string_or_none(record.get("テロップ"))
            packs = ensure_list(record.get("パック"))
            timeline_objects: list[TimelineObject] = []
            for column in object_columns:
                identifier = _string_or_none(record.get(column))
                if not identifier:
                    continue
                role = column
                layer_band = data.layers.get(role)
                layer = layer_band.layer if layer_band else None
                resolved = data.assets.get(identifier)
                timeline_objects.append(
                    TimelineObject(role=role, identifier=identifier, layer=layer, resolved=resolved)
                )
            timeline_fxs: list[TimelineFx] = []
            for column in fx_columns:
                fx_identifier = _string_or_none(record.get(column))
                if not fx_identifier:
                    continue
                resolved = data.fx_presets.get(fx_identifier)
                params = {}
                fx_param_value = record.get(fx_param_key)
                if isinstance(fx_param_value, str):
                    params = parse_mapping(fx_param_value)
                timeline_fxs.append(TimelineFx(fx_id=fx_identifier, parameters=params, resolved=resolved))
            notes = {key: value for key, value in record.items() if key not in {
                "開始",
                "終了",
                "字幕テキスト",
                "テロップ",
                "パック",
            }.union(object_columns, fx_columns, {fx_param_key})}
            data.timeline.append(
                TimelineRow(
                    index=index,
                    start=start,
                    end=end,
                    subtitle=subtitle,
                    telop=telop,
                    packs=packs,
                    objects=timeline_objects,
                    fxs=timeline_fxs,
                    notes=notes,
                )
            )

    return data


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value)
