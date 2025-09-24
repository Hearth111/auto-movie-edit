"""Utilities for reading history logs and summarising warnings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


@dataclass
class HistoryLoadResult:
    """Represents the outcome of loading history entries from jsonl files."""

    entries: List[Dict[str, Any]]
    errors: List[str]


WarningSummary = Dict[str, Any]


WARNING_HINTS: List[Tuple[str, str, str]] = [
    (
        "Unresolved template path",
        "未解決テンプレートパス",
        "テンプレートの `source` やファイルパスが誤っている可能性があります。"
        " 辞書のパスを実ファイルと突き合わせて修正してください。",
    ),
    (
        "Layer band overflow",
        "レイヤ帯オーバーフロー",
        "配置レイヤが帯域の上限を超えました。バンド幅設定や優先度を見直し、"
        " 重要度の低いアイテムを別帯に移すか、自動割り当ての基準を調整してください。",
    ),
    (
        "Telop pattern not found",
        "未登録テロップID",
        "TIMELINEのテロップIDが辞書に存在しません。テロップシートへ登録するか、"
        " 正しいIDに修正してください。",
    ),
    (
        "Telop build error",
        "テロップ生成エラー",
        "テンプレート適用時に例外が発生しました。テンプレートJSONの形式と差し替え値を"
        " 確認してください。",
    ),
    (
        "Character not found",
        "キャラクター未登録",
        "立ち絵キャラクター名が辞書に存在しません。キャラクター設定シートを更新してください。",
    ),
    (
        "No expressions provided",
        "立ち絵差分未設定",
        "対象キャラクターに必要な表情差分が登録されていません。差分パスを設定してください。",
    ),
    (
        "Unknown tachie part",
        "未知の立ち絵パーツ",
        "辞書にないパーツ名が指定されています。パーツ名を既存のキーに合わせてください。",
    ),
    (
        "Tachie base path missing",
        "立ち絵テンプレート欠損",
        "立ち絵テンプレートの参照パスが不足しています。ベースとなるパーツのパスを確認してください。",
    ),
    (
        "Dynamic Tachie build error",
        "立ち絵生成エラー",
        "立ち絵生成中にエラーが発生しました。辞書の差分指定やテンプレート構造を確認してください。",
    ),
    (
        "Pack not found",
        "パック未登録",
        "パックIDが辞書に存在しません。複数オブジェクトシートを更新するか、IDを修正してください。",
    ),
    (
        "Pack '",
        "パックテンプレート不備",
        "パックのテンプレート内容が不足しています。itemsやテンプレートJSONの内容を確認してください。",
    ),
    (
        "Asset not found",
        "オブジェクト未登録",
        "単体オブジェクトIDが辞書にありません。オブジェクトシートに登録するか、IDを修正してください。",
    ),
    (
        "Asset '",
        "オブジェクトテンプレート不備",
        "オブジェクトテンプレートの必須パラメータが欠けています。テンプレートJSONと差分を確認してください。",
    ),
    (
        "FX preset not found",
        "FXプリセット未登録",
        "FXプリセットIDが辞書に存在しません。FX定義を追加するか、IDを修正してください。",
    ),
    (
        "FX preset '",
        "FXプリセット設定不備",
        "FXプリセットの参照パックや素材パスが不足しています。参照先が存在するか確認してください。",
    ),
    (
        "FX '",
        "FX上書き不整合",
        "FXのベースパラメータが未定義のまま上書きが指定されています。プリセット定義を見直してください。",
    ),
]


def load_history_entries(history_path: Path, latest_only: bool = False) -> HistoryLoadResult:
    """Load history entries from ``history_path``.

    ``history_path`` can be either a directory containing dated folders or a jsonl file.
    When ``latest_only`` is ``True``, only the most recently modified jsonl file is read.
    """

    entries: List[Dict[str, Any]] = []
    errors: List[str] = []

    if not history_path.exists():
        return HistoryLoadResult(entries=[], errors=[f"History path not found: {history_path}"])

    jsonl_files: List[Path]
    if history_path.is_file():
        jsonl_files = [history_path]
    else:
        jsonl_files = sorted(history_path.glob("**/history.jsonl"))
        if latest_only and jsonl_files:
            latest_file = max(jsonl_files, key=lambda path: path.stat().st_mtime)
            jsonl_files = [latest_file]

    for jsonl_file in jsonl_files:
        try:
            text = jsonl_file.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - unlikely, but defensive.
            errors.append(f"{jsonl_file}: {exc}")
            continue

        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entries.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                errors.append(f"{jsonl_file}:{line_number} JSON decode error: {exc}")

    return HistoryLoadResult(entries=entries, errors=errors)


def classify_warning(message: str) -> Tuple[str, str]:
    """Return a tuple of (label, hint) for the provided warning message."""

    lowered = message.lower()
    for keyword, label, hint in WARNING_HINTS:
        if keyword.lower() in lowered:
            return label, hint
    return "その他の警告", "詳細は history.jsonl のメッセージを直接確認してください。"


def summarize_warnings(entries: Iterable[Dict[str, Any]]) -> List[WarningSummary]:
    """Aggregate warning counts and provide hints for remediation."""

    summary: Dict[str, Dict[str, Any]] = {}

    for entry in entries:
        warnings = entry.get("warnings") or []
        if not isinstance(warnings, list):
            continue
        row_index = entry.get("row_index") or entry.get("row") or entry.get("rowIndex")
        for warning in warnings:
            if not isinstance(warning, str):
                continue
            label, hint = classify_warning(warning)
            data = summary.setdefault(
                label,
                {"label": label, "count": 0, "hint": hint, "rows": set(), "messages": set()},
            )
            data["count"] += 1
            data["messages"].add(warning)
            if row_index is not None:
                data["rows"].add(str(row_index))

    ordered: List[WarningSummary] = []
    for data in summary.values():
        ordered.append(
            {
                "label": data["label"],
                "count": data["count"],
                "hint": data["hint"],
                "rows": sorted(data["rows"]),
                "messages": sorted(data["messages"]),
            }
        )

    ordered.sort(key=lambda item: item["count"], reverse=True)
    return ordered

