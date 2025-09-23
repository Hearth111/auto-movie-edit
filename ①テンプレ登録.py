import sys
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

# --- 準備 ---
script_path = Path(__file__).resolve()
project_root = script_path.parent
src_path = project_root / 'src'
sys.path.insert(0, str(src_path))
from auto_movie_edit.cli import absorb

# --- UIによるファイル選択処理 ---
def select_files():
    """ファイル選択ダイアログを表示して、ymmpとxlsxのパスを取得する"""
    # UIウィンドウの準備
    root = tk.Tk()
    root.withdraw() # ウィンドウは表示しない

    print("--- ファイルを選択してください ---")
    
    # YMMPファイルの選択ダイアログを表示
    ymmp_file = filedialog.askopenfilename(
        title="1. 吸収するYMMPファイルを選択してください",
        filetypes=[("YMM4 Project File", "*.ymmp")]
    )
    if not ymmp_file:
        print("YMMPファイルの選択がキャンセルされました。処理を中断します。")
        return None, None
    
    print(f"✔️ YMMPファイル: {Path(ymmp_file).name}")

    # XLSXファイルの選択ダイアログを表示
    workbook_file = filedialog.askopenfilename(
        title="2. 登録先のスプレッドシートを選択してください",
        filetypes=[("Excel Workbook", "*.xlsx")]
    )
    if not workbook_file:
        print("Excelファイルの選択がキャンセルされました。処理を中断します。")
        return None, None

    print(f"✔️ Excelファイル: {Path(workbook_file).name}\n")
    return Path(ymmp_file), Path(workbook_file)

# --- 実行処理 ---
def main():
    """ファイルを選択し、absorbコマンドを実行する"""
    ymmp_file, workbook_file = select_files()

    if not ymmp_file or not workbook_file:
        return # ファイル選択がされなかった場合は終了

    print("--- absorb処理を開始します ---")
    try:
        # absorb関数を実行
        absorb(ymmp=ymmp_file, xlsx=workbook_file)
        print("\n--- 正常に処理が完了しました ---")
        print(f"{workbook_file.name} が更新されました。")
    except Exception as e:
        print(f"\n--- エラーが発生しました ---")
        print(f"エラー内容: {e}")

if __name__ == "__main__":
    main()