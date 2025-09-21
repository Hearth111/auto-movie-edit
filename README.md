要件定義：YMM4直変換・台帳駆動のショート動画生成
0. 目的

VrewのSRTと「台帳（スプレッドシート/Excel）」を入力に、.ymmp を自動生成。

テロップ・立ち絵・効果音・背景に加え、ズーム、集中線、シェイク等の演出を定義済みパターン/パックとして適用。

運用では、台帳のプルダウン選択と最小限の手修正のみで量産可能にする。

1. 用語

台帳：TIMELINEシート（行＝1カット）。左→右の列が前面→背面（Z順）。

単一オブジェクト：画像/音声/動画/テキスト等の単品素材。

パック（複数オブジェクト）：Group/Tachie/複数のItem＋エフェクト設定を束ねたテンプレ群。

テロップパターン：ベースTextItem＋（必要なら）Group/装飾を含むテロップ専用パック。

演出（FX）：ズーム、集中線、シェイク、ビネット、モーションブラー等。単一オブジェクトまたはパックで表現。

2. データモデル（スプレッドシート構成）
2.1 シート一覧

テロップパターン（TELP_PATTERNS）

単一オブジェクト（ASSETS_SINGLE）

複数オブジェクト（PACKS_MULTI）

レイヤ割り当て（LAYERS）

TIMELINE（配置指示・左→右＝前→後）

SCHEMA_MAP（日本語→内部キー対応。実行時に参照）

2.2 推奨カラム
テロップパターン

パターンID（主キー）

参照ソース（例：template://packs/telop_emphasis_yellow.json）

上書きキー（例：Text,Frame,Length,X,Y,Zoom,FilePath）

基準幅/基準高さ/FPS（メタ）

説明/備考

単一オブジェクト

素材ID（主キー）

種別（image|audio|video|text|effect）

パス（相対/絶対。template://...可）

既定レイヤ/既定X/既定Y/既定ズーム

備考

複数オブジェクト

パックID（主キー）

参照ソース（template://packs/*.json）

上書きキー（例：Text,FilePath,Frame,Length,X,Y,Zoom）

基準幅/基準高さ/FPS

備考

レイヤ割り当て

役割 → レイヤ（帯の基準値）

例：テロップ=80、オブジェクト1=70、オブジェクト2=60、オブジェクト3=50、効果線=55、背景=10、効果音=20

TIMELINE（例）

開始 / 終了（HH:MM:SS.mmm）

字幕 / テロップ（パターンID） / パック（パックID）

オブジェクト1 / オブジェクト2 / オブジェクト3 / 背景（＝素材ID or 直パス）

効果音オフセット / X / Y / ズーム / フェードイン / フェードアウト

演出列（FX）：

FX_ズーム（zoom_in_fast / zoom_out_soft / …）

FX_集中線（speedlines_dense / speedlines_soft / …）

FX_シェイク（shake_light / shake_heavy / …）

FX_ビネット（vignette_soft / …）

FX_モーションブラー（mblur_short / …）

各FXの強度/中心/角度などは FX_PARAM 列にJSONで追記可（{"center":"0, -200","amount":0.3} など）

承認（AI提案の採否） / メモ

プルダウン：テロップ→テロップパターン、パック→複数オブジェクト、オブジェクト*→単一オブジェクト、FX_*→定義済みFX ID。

3. 演出（FX）仕様
3.1 モデル化

ズーム：

type: zoom / preset: zoom_in_fast|zoom_out_soft|…

実装方法：

RepeatZoom系エフェクトのプリセットを持つパックとして適用

または対象Itemの Zoom キーフレームを生成（パック化推奨）

集中線（スピードライン）：

type: speedlines / preset: speedlines_dense|soft|burst

実装方法：半透明PNGの単一オブジェクト（image）またはパック（回転/拡大/合成モード設定込み）

シェイク：

type: shake / preset: shake_light|shake_heavy

実装方法：対象Groupに位置揺れキーを持つパックを重ねる（X/Yのノイズキーフレーム）

ビネット/モーションブラー：

type: vignette|motionblur / preset: vignette_soft|mblur_short

実装方法：単一オブジェクト（オーバーレイ）or パック（ブレ強度のエフェクト含む）

原則：FXは“パック優先”。適用時はFrame/Length/Layerを帯に合わせて再マップ。必要差分は override_keys で上書き。

4. レイヤとZ順

規則：TIMELINEの列は左→右が前→後。

帯幅：各スロットは 10レイヤ幅を確保（例：テロップ=80–89、Obj1=70–79、…）。

パック適用：パック内部の Layer を 最小値基準で正規化 → 対象帯の中に相対順キープで再配置（溢れはクリップ＆警告）。

固定役割（効果音/背景など）は専用帯に常設。

5. 変換パイプライン

入力：SRT / シート（CSV） / 既存パックJSON（template://packs/*.json）

辞書ロード：テロップ/単一/複数パック/レイヤ/スキーマ

TIMELINE走査（上から順、左→右の列順で適用）

テロップ → テロップパターンをクローン、Text/Frame/Length…を上書き

パック → クローン適用（差分上書き）

オブジェクト* → 単一オブジェクトとして生成

FX_* → FXパックをクローン適用（なければ単一オブジェクト/簡易キー生成）

ひらがな縮小フィルタ：既存Decorationsを保ちつつ、ひらがな位置の Scale *= 0.85 をマージ

検証：パス切れ/ID不正/FPS不一致/帯溢れ/重複レイヤの警告レポート出力

出力：.ymmp（work/out.ymmp）＋レポート（work/report.json）

6. パック抽出・登録

抽出器（ymmp_to_sheets.py拡張）：.ymmpから

テロップ候補：Textを含む近接群 or Group配下

複数パック候補：Group/Tachie/Repeat系を含む群

FX候補：集中線PNGオーバーレイ、ズーム/シェイク等を含む群
を拾い、template://packs/*.json として保存、各シートに追記（重複はハッシュIDで排除）。

override_keys の既定：Text,FilePath,Frame,Length,X,Y,Zoom（必要に応じ追加可）。

7. AI提案と学習

初期提案：SRTテキストから テロップID / オブジェクト / FX を軽量ルールで仮埋め。

採否：承認列がTRUEなら正例、編集されてFALSEなら負例として history.jsonl に差分保存。

オンライン更新：辞書（語→表情/SE/FX）に勝ち負けを反映。モデル導入は任意で段階的。

8. バリデーション/エラーハンドリング

必須：開始/終了/テロップ（任意）/パック（任意）/オブジェクト*（任意）/FX_*（任意）

ファイル存在：パス参照は存在確認、欠損は警告＋その行スキップ。

FPS/解像度差：パックのメタとプロジェクトが異なる場合は警告。

帯溢れ：パック内部レイヤ幅が帯を超える場合、上限でクリップし警告を記録。

IME/文字：字幕テキストはUTF-8で保持、改行は \n。

9. パフォーマンス/運用

30秒ショート×数十本を想定。1本の生成時間は数秒〜十数秒を目標（環境依存）。

生成前に自動バックアップ（out_<timestamp>.ymmp）。

すべての成果物を work/ に集約（out.ymmp/report.json/history.jsonl）。

10. 実装インターフェース（例）
10.1 CLI
# 1) SRT→TIMELINE雛形（AI仮埋め）
cli make-sheet --srt in.srt --out sheet.xlsx

# 2) YMMPを辞書に吸収
cli absorb --ymmp template.ymmp --xlsx sheet.xlsx

# 3) 台帳→YMMP（直変換）
cli build --sheet sheet.xlsx --out work/out.ymmp

# 4) フィルタ（ひらがな縮小）
cli filter hira-shrink --in work/out.ymmp --scale 0.85 --out work/out_shrink.ymmp

10.2 FX定義（内部プリセットの例・JSON）
{
  "fx": {
    "zoom_in_fast":   {"type":"zoom","pack":"fx_zoom_in_fast"},
    "zoom_out_soft":  {"type":"zoom","pack":"fx_zoom_out_soft"},
    "speedlines_soft":{"type":"speedlines","pack":"fx_speedlines_soft"},
    "shake_light":    {"type":"shake","pack":"fx_shake_light"},
    "vignette_soft":  {"type":"vignette","asset":"assets/fx/vignette_soft.png"},
    "mblur_short":    {"type":"motionblur","pack":"fx_mblur_short"}
  }
}

11. 例：TIMELINEの1行 → 生成物
開始=00:00:03.000 / 終了=00:00:05.200
字幕=「マジ!?」 / テロップ=telop_強調黄
パック=（空） / オブジェクト1=立ち絵_驚き / オブジェクト2=SE_ポップ
FX_ズーム=zoom_in_fast / FX_集中線=speedlines_soft


→ 処理順

テロップパターンをFrame/Length差し替えでクローン（帯=80–89）

立ち絵/SEを各帯へ配置（70–79 / 20–29）

FXズーム/集中線のパックを帯へ再マップ（例：ズーム=75–79、集中線=55–59）

ひらがな縮小をマージ

out.ymmp 出力

12. セキュリティ/パス

プロジェクトルートを基準に相対パス優先。外部ドライブはUNC/絶対で許容（存在チェック必須）。

template:// 参照は実体JSONを packs/ 配下に保存。

13. テスト観点

Z順：列順→レイヤ帯→相対順の保持

FX：ズーム/集中線/シェイクの同時適用（帯が干渉しないこと）

パック差分：override_keys が期待どおり反映

ひらがな縮小：Decorationsの上書きにならず乗算マージ

欠損：素材欠落・パス切れの警告生成

異FPS：警告のみで処理継続
