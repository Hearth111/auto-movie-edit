import sys
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
import traceback
from datetime import datetime

# --- エラーログをファイルに書き込む設定 ---
def log_exception_to_file(exc_info):
    """Saves detailed exception info to a log file."""
    log_file_path = Path(__file__).parent / "error_log.txt"
    with open(log_file_path, "w", encoding="utf-8") as f:
        f.write(f"--- Error Log [{datetime.now()}] ---\n\n")
        traceback.print_exception(exc_info[0], exc_info[1], exc_info[2], file=f)
    return log_file_path

# --- UI付きスクリプト本体 ---
def main_wrapper():
    # このtry...exceptが、どんなエラーでもキャッチします
    try:
        # --- 準備 ---
        script_path = Path(__file__).resolve()
        project_root = script_path.parent
        src_path = project_root / 'src'
        sys.path.insert(0, str(src_path))
        from auto_movie_edit.cli import build

        # --- UIによるファイル選択処理 ---
        def select_files():
            root = tk.Tk()
            root.withdraw()
            print("--- YMMPビルドプロセスを開始します ---")
            
            workbook_file = filedialog.askopenfilename(
                title="1. 読み込む台帳（Excelファイル）を選択してください",
                filetypes=[("Excel Workbook", "*.xlsx")]
            )
            if not workbook_file:
                print("Excelファイルの選択がキャンセルされました。")
                return None, None
            print(f"✔️ 台帳ファイル: {Path(workbook_file).name}")

            output_dir = filedialog.askdirectory(
                title="2. YMMPファイルの出力先フォルダを選択してください",
                initialdir=project_root
            )
            if not output_dir:
                print("出力先フォルダの選択がキャンセルされました。")
                return None, None

            return Path(workbook_file), Path(output_dir)

        # --- 実行処理本体 ---
        workbook_file, output_dir = select_files()
        if not workbook_file or not output_dir:
            print("処理を中断しました。")
            return
            
        build(sheet=workbook_file, out=output_dir)
        print(f"\n--- 正常に処理が完了しました ---")
        print(f"YMMPプロジェクトが出力されました: {output_dir}")

    except Exception:
        # エラーが発生したら、それをファイルに書き出す
        log_path = log_exception_to_file(sys.exc_info())
        print("\n--- 重大なエラーが発生しました ---")
        print(f"エラーの詳細がログファイルに記録されました: {log_path}")
    finally:
        # 正常終了でもエラー終了でも、必ず最後にここで一時停止する
        print("\n--- Enterキーを押してウィンドウを閉じてください ---")
        input()

if __name__ == "__main__":
    main_wrapper()