"""Command line interface for the auto_movie_edit toolkit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

import typer
from openpyxl import load_workbook

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


@app.command("absorb")
def absorb(
    ymmp: Path = typer.Option(..., exists=True, dir_okay=False, readable=True, help="Source YMMP JSON"),
    xlsx: Path = typer.Option(..., dir_okay=False, help="Workbook to update"),
) -> None:
    """Absorb a YMMP file into the workbook dictionaries."""

    project = json.loads(ymmp.read_text(encoding="utf-8"))

    if xlsx.exists():
        workbook = load_workbook(xlsx)
    else:
        workbook = create_workbook_template(DEFAULT_TEMPLATE)

    _sync_dictionary_sheet(workbook, "TELP_PATTERNS", DEFAULT_TEMPLATE.telp_headers, project.get("telop_patterns", {}))
    _sync_dictionary_sheet(workbook, "ASSETS_SINGLE", DEFAULT_TEMPLATE.asset_headers, project.get("assets", {}))
    _sync_dictionary_sheet(workbook, "PACKS_MULTI", DEFAULT_TEMPLATE.pack_headers, project.get("packs", {}))
    _sync_dictionary_sheet(workbook, "FX", DEFAULT_TEMPLATE.fx_headers, project.get("fx_presets", {}))
    _sync_dictionary_sheet(workbook, "LAYERS", DEFAULT_TEMPLATE.layer_headers, project.get("layers", {}))

    save_workbook(workbook, xlsx)
    typer.secho(f"Workbook updated with project dictionaries -> {xlsx}", fg=typer.colors.GREEN)


def _sync_dictionary_sheet(workbook, name: str, headers: Iterable[str], values: dict) -> None:
    header_list = list(headers)
    if name in workbook.sheetnames:
        sheet = workbook[name]
        if sheet.max_row < 1:
            _write_headers(sheet, header_list)
    else:
        sheet = workbook.create_sheet(name)
        _write_headers(sheet, header_list)

    existing_ids = set()
    id_column = 1
    for row_index in range(2, sheet.max_row + 1):
        value = sheet.cell(row=row_index, column=id_column).value
        if value:
            existing_ids.add(str(value))

    for key, payload in values.items():
        identifier = str(key)
        if identifier in existing_ids:
            continue
        row_index = sheet.max_row + 1
        sheet.cell(row=row_index, column=1, value=identifier)
        for column, header in enumerate(header_list[1:], start=2):
            if isinstance(payload, dict):
                cell_value = payload.get(_map_field_name(header))
            else:
                cell_value = None
            if isinstance(cell_value, (dict, list)):
                cell_value = json.dumps(cell_value, ensure_ascii=False)
            sheet.cell(row=row_index, column=column, value=cell_value)
        existing_ids.add(identifier)


def _write_headers(sheet, headers: Iterable[str]) -> None:
    for column, header in enumerate(headers, start=1):
        sheet.cell(row=1, column=column, value=header)


def _map_field_name(header: str) -> str:
    mapping = {
        "参照ソース": "source",
        "上書きキー": "overrides",
        "基準幅": "base_width",
        "基準高さ": "base_height",
        "FPS": "fps",
        "説明": "description",
        "備考": "notes",
        "種別": "kind",
        "パス": "path",
        "既定レイヤ": "default_layer",
        "既定X": "default_x",
        "既定Y": "default_y",
        "既定ズーム": "default_zoom",
        "役割": "role",
        "レイヤ帯": "layer",
        "種類": "fx_type",
        "パック": "source",
        "アセット": "asset",
        "パラメータ": "parameters",
    }
    return mapping.get(header, header)


if __name__ == "__main__":
    app()
