import sys
from pathlib import Path

# このスクリプト自身の絶対パスを取得
# これにより、どこから実行してもスクリプトの場所が基準になります
script_path = Path(__file__).resolve()
project_root = script_path.parent

# 'src' フォルダの場所をPythonに教える
src_path = project_root / 'src'
sys.path.insert(0, str(src_path))

from auto_movie_edit.workbook import create_workbook_template, save_workbook

# --- パスの指定方法を修正 ---

# スクリプトと同じ階層にある 'Template' フォルダを指定
output_folder = project_root / "Template"

# フォルダが存在しない場合は作成する
output_folder.mkdir(exist_ok=True)

# 出力ファイル名を指定（フォルダの中に入るようにパスを結合）
output_file = output_folder / "template.xlsx"

# --- 修正ここまで ---

# テンプレートのワークブックを生成
print("ワークブックテンプレートを生成しています...")
workbook = create_workbook_template()

# ファイルとして保存
save_workbook(workbook, output_file)

print(f"テンプレートが作成されました: {output_file.absolute()}")