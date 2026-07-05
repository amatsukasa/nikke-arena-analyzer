# ローカル開発ファイルの扱い

## 一時ファイル

ログ、比較画像、途中生成物、単発の調査・復旧スクリプトは `.local/`、`tmp/`、または `scratch/` に置きます。これらは Git 管理しません。

## コードとテスト

- 本番コードは既存の `backend/`、`frontend/` の構成に従って配置します。
- 継続利用する補助スクリプトは `backend/scripts/` など既存の scripts ディレクトリへ置きます。
- 再現可能な正式テストは `backend/tests/` など既存のテストディレクトリへ置きます。
- `backend/` 直下の `test_*.py` はアドホック検証用として扱い、正式テストに昇格させる場合は内容を整理して `backend/tests/` へ移します。

## uploads

`backend/uploads/templates/` は画像認識に必要なテンプレート置き場であり、Git 管理対象です。`backend/uploads/` 全体を削除・ignoreしないでください。

`backend/uploads/cropped/` と `backend/uploads/player_icons/` はランタイム生成物であり、Git 管理しません。

## staging

`git add .` は使いません。`git status --short` を確認し、必要なファイルだけパス指定で追加します。
