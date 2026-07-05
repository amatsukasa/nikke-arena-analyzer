# コレクション情報バッジの画像判定

`backend/services/collection_classifier.py` は、キャラクター切り出し画像を
160×160へ正規化し、左端の固定ROIだけを使ってバッジを判定します。OCRや
学習モデルは使用しません。

解析画面では、ブラウザが白いモーダル領域を検出してPNGのままロスレスで
切り出してから送信します。`image_pre_cropped=true` が付いた画像については、
バックエンドの既存モーダル検出をスキップし、二重切り出しを防ぎます。
ブラウザ側で検出できなかった場合は元画像をそのまま送り、バックエンド側の
既存検出へフォールバックします。

解析後は用途別に画像を分けます。

- テンプレート候補: 160×160のロスレスPNG。テンプレート登録時はPNG圧縮
  レベル9で再保存し、画素を変えずに容量を削減します。
- 画面プレビュー: WebP品質55。目視確認専用で、テンプレート照合には使いません。

登録完了後は、テンプレートとして採用したロスレス画像を除き、PNGとWebPの
一時cropを両方削除します。未登録の一時cropも既存のstale cleanup対象です。

判定は次の順序です。

1. HSV色マスクから、固定位置・固定サイズに収まる連結成分を抽出する
2. 面積、位置、充填率、凸包に対するsolidityを組み合わせてバッジ有無を判定する
3. 採用した形状の色相から `r` / `sr` / `treasure` を判定する
4. バッジ内側の暗色画素比率からLv15版を判定する

0～14のバッジは画像だけで正確なレベル数値を特定できないため、
`level` は `null`、`debug_info.level_band` は `0_14` とします。
Lv15は `level: 15` を返します。従来の `collection_level` と
`collection_confidence` も引き続き返します。

## デバッグ

`process_images(..., debug=True)` または
`analyze_collection(..., debug=True)` を使用すると、既定では
`.local/collection-debug/` に正規化画像、ROI、レアリティ別マスク、
採用した矩形付き画像を保存します。

## 確認

バックエンドディレクトリで次を実行します。

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

実画像fixtureは `backend/tests/fixtures/collection/` にあり、
`expected.json` に期待値を定義しています。
