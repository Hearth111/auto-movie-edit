"""Command line interface for the auto_movie_edit toolkit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import typer
from openpyxl import Workbook, load_workbook

from .srt import SrtParseError, parse_srt
from .workbook import (
    DEFAULT_TEMPLATE,
    create_workbook_template,
    load_workbook_data,
    save_workbook,
)
from .ymmp import apply_hiragana_shrink, build_project, write_outputs

app = typer.Typer(help="Auto Movie Edit CLI utilities")


@app.command("make-sheet")
def make_sheet(
    srt: Path = typer.Option(..., exists=True, dir_okay=False, readable=True, help="SRT subtitle file"),
    out: Path = typer.Option(..., dir_okay=False, help="Output Excel file"),
) -> None:
    """Create a workbook template populated with SRT subtitles."""
    try:
        entries = parse_srt(srt)
    except SrtParseError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    workbook = create_workbook_template(DEFAULT_TEMPLATE)
    timeline_sheet = workbook["TIMELINE"]

    for row_index, entry in enumerate(entries, start=2):
        timeline_sheet.cell(row=row_index, column=1, value=entry.start.to_string())
        timeline_sheet.cell(row=row_index, column=2, value=entry.end.to_string())
        timeline_sheet.cell(row=row_index, column=3, value=entry.text)

    save_workbook(workbook, out)
    typer.secho(f"Workbook created: {out}", fg=typer.colors.GREEN)


@app.command("build")
def build(
    sheet: Path = typer.Option(..., exists=True, dir_okay=False, readable=True, help="Timeline workbook"),
    out: Path = typer.Option(Path("work"), file_okay=False, dir_okay=True, help="Output directory"),
) -> None:
    """Build a simplified YMMP project from the workbook."""
    data = load_workbook_data(sheet)
    project, warnings = build_project(data)
    write_outputs(project, warnings, out)
    typer.secho(f"Project generated with {len(warnings)} warnings -> {out}", fg=typer.colors.GREEN)


@app.command("filter")
def filter_command(
    filter_name: str = typer.Argument(..., help="Filter name"),
    input_path: Path = typer.Option(..., exists=True, dir_okay=False, help="Input YMMP JSON"),
    out: Path = typer.Option(..., dir_okay=False, help="Output YMMP JSON"),
    scale: Optional[float] = typer.Option(0.85, help="Scale applied to telop text"),
) -> None:
    """Apply post-processing filters to a project."""
    filter_name = filter_name.lower()
    if filter_name == "hira-shrink":
        apply_hiragana_shrink(input_path, out, scale or 0.85)
        typer.secho(f"Hiragana shrink applied -> {out}", fg=typer.colors.GREEN)
    else:
        typer.secho(f"Unknown filter: {filter_name}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


def _extract_telops_from_raw_ymmp(project: dict, xlsx_path: Path) -> dict:
    """Extracts TextItems and saves them as templates."""
    typer.secho("Extracting telop patterns...", fg=typer.colors.CYAN)
    extracted = {}
    template_dir = xlsx_path.parent / "templates" / "telops"
    template_dir.mkdir(parents=True, exist_ok=True)

    items = project.get("Timelines", [{}])[0].get("Items", [])
    for item in items:
        if "TextItem" in item.get("$type", ""):
            text = item.get("Text", "no_text")
            pattern_id = f"telop_{text}"
            if pattern_id in extracted: continue

            template_file_path = template_dir / f"{pattern_id}.json"
            template_file_path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")

            extracted[pattern_id] = {
                "pattern_id": pattern_id,
                "source": template_file_path.resolve().as_posix(),
                "description": f"「{text}」から自動抽出",
            }
    typer.secho(f"Found {len(extracted)} telop patterns.", fg=typer.colors.GREEN)
    return extracted

def _extract_assets_from_raw_ymmp(project: dict, xlsx_path: Path) -> dict:
    """Extracts TachieItems/ImageItems and saves them as templates."""
    typer.secho("Extracting asset patterns...", fg=typer.colors.CYAN)
    extracted = {}
    template_dir = xlsx_path.parent / "templates" / "assets"
    template_dir.mkdir(parents=True, exist_ok=True)

    items = project.get("Timelines", [{}])[0].get("Items", [])
    for item in items:
        item_type = item.get("$type", "")
        asset_id = None
        kind = None

        if "TachieItem" in item_type:
            kind = "tachie"
            char_name = item.get("CharacterName", "unknown")
            # 表情をファイル名から推測
            eye_path = Path(item.get("TachieItemParameter", {}).get("Eye", ""))
            emotion = eye_path.stem.split("】")[-1] if "】" in eye_path.stem else "default"
            asset_id = f"tachie_{char_name}_{emotion}"
            
        elif "ImageItem" in item_type:
            kind = "image"
            file_path = Path(item.get("FilePath", ""))
            asset_id = f"image_{file_path.stem}"

        if asset_id and asset_id not in extracted:
            template_file_path = template_dir / f"{asset_id}.json"
            template_file_path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
            
            extracted[asset_id] = {
                "asset_id": asset_id,
                "kind": kind,
                "path": template_file_path.resolve().as_posix(),
                "notes": f"from {Path(project.get('FilePath')).name}",
            }
    typer.secho(f"Found {len(extracted)} asset patterns.", fg=typer.colors.GREEN)
    return extracted


@app.command("absorb")
def absorb(
    ymmp: Path = typer.Option(..., exists=True, dir_okay=False, readable=True, help="Source YMMP JSON"),
    xlsx: Path = typer.Option(..., dir_okay=False, help="Workbook to update"),
) -> None:
    """Absorb a YMMP file into the workbook dictionaries."""
    try:
        project = json.loads(ymmp.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        typer.secho(f"Error reading YMMP file: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if xlsx.exists():
        workbook = load_workbook(xlsx)
    else:
        workbook = create_workbook_template(DEFAULT_TEMPLATE)
        
    if "telop_patterns" in project or "assets" in project: # Tool-generated file
        telop_patterns = project.get("telop_patterns", {})
        assets = project.get("assets", {})
    else: # Raw YMM4 file
        telop_patterns = _extract_telops_from_raw_ymmp(project, xlsx)
        assets = _extract_assets_from_raw_ymmp(project, xlsx)

    _sync_dictionary_sheet(workbook, "TELP_PATTERNS", DEFAULT_TEMPLATE.telp_headers, telop_patterns)
    _sync_dictionary_sheet(workbook, "ASSETS_SINGLE", DEFAULT_TEMPLATE.asset_headers, assets)
    
    save_workbook(workbook, xlsx)
    typer.secho(f"Workbook updated with project dictionaries -> {xlsx}", fg=typer.colors.GREEN)


def _sync_dictionary_sheet(workbook: Workbook, name: str, headers: Iterable[str], values: dict) -> None:
    header_list = list(headers)
    sheet = workbook[name] if name in workbook.sheetnames else workbook.create_sheet(name)

    if sheet.max_row < 1: _write_headers(sheet, header_list)
        
    existing_ids = {str(sheet.cell(row=r, column=1).value) for r in range(2, sheet.max_row + 1)}

    for key, payload in values.items():
        if str(key) in existing_ids: continue
        
        new_row_index = sheet.max_row + 1
        for col_idx, header in enumerate(header_list, start=1):
            field_name = _map_header_to_field(header)
            # Use key as the default for the first column's field name
            is_id_column = (field_name == header_list[0].lower().replace(" ", "_")) or \
                           (field_name in ["pattern_id", "asset_id", "pack_id", "fx_id"])
            
            cell_value = key if is_id_column else payload.get(field_name)

            if isinstance(cell_value, (dict, list)) and cell_value:
                cell_value = json.dumps(cell_value, ensure_ascii=False)
            elif isinstance(cell_value, (dict, list)):
                cell_value = None

            sheet.cell(row=new_row_index, column=col_idx, value=cell_value)
        existing_ids.add(str(key))


def _write_headers(sheet, headers: Iterable[str]) -> None:
    for column, header in enumerate(headers, start=1):
        sheet.cell(row=1, column=column, value=header)


def _map_header_to_field(header: str) -> str:
    mapping = {
        "パターンID": "pattern_id", "参照ソース": "source", "上書きキー": "overrides",
        "説明": "description", "備考": "notes", "素材ID": "asset_id", "種別": "kind",
        "パス": "path", "既定レイヤ": "default_layer", "既定X": "default_x",
        "既定Y": "default_y", "既定ズーム": "default_zoom", "パックID": "pack_id",
        "役割": "role", "レイヤ帯": "layer", "FX_ID": "fx_id", "種類": "fx_type",
        "パック": "source", "アセット": "asset", "パラメータ": "parameters",
    }
    return mapping.get(header, header.lower().replace(" ", "_"))

if __name__ == "__main__":
    app()