# 大会206の旧リーグ戦と編成の紐づけ

対象は正式64人モードの大会206です。現行プログラムに補正ツールと集計側の対応をデプロイしてから実行します。デプロイだけで既存の大会に補正は入りません。編成や試合結果を提供者が再登録する操作はありません。

## 1. 本番作業の準備

- レビュー済みのコミットが Railway の本番バックエンドにデプロイされ、起動とDBマイグレーションが成功していることを確認します。補正内容は新しい `arena_legacy_league_link_batches` テーブルに保存されます。
- Railway 管理画面で本番の Project、Environment、Backend Service と接続先 PostgreSQL のデータベース名を照合し、DBの復元可能なバックアップを確認します。作業担当者、時刻、対象大会を記録します。
- 手元の端末から本番バックエンドへ接続します。接続先を入れ替えてから実行してください。

```sh
railway ssh --project <PROJECT_ID> --environment <PRODUCTION_ENVIRONMENT_ID> --service <BACKEND_SERVICE_ID>
```

以下は接続先コンテナのシェルで実行します。DB名には管理画面で照合した実際の名前を設定します。トークンやDB接続文字列をコマンド履歴や作業記録に貼らないでください。

```sh
cd /app
EXPECTED_DB='確認済みの本番DB名'
python -m scripts.link_legacy_league --help
```

## 2. 読み取り専用プレビュー

```sh
python -m scripts.link_legacy_league preview --tournament-id 206 --expect-database "$EXPECTED_DB"
```

- 大会名とIDを確認します。提供済みJSONと同じ内容なら `matches: 56`、`player_links: 112`、`skipped: []`、初回は `active_digest: null` です。ベスト8以降の結果版付き7試合は候補に含まれません。
- JSONの `links` に、旧試合ID、両選手のID、編成番号と25枠、5ラウンドの勝者、その試合に基づく成績が出ます。既存の候補一覧と照合し、件数や紐づけ先が違えば適用を見送り、差分を調べてください。
- 確認した出力と `digest` をアクセス制限のある作業記録に保存してください。これは確認時点の候補を識別するハッシュです。プレビューはPostgreSQLの読み取り専用トランザクションで実行されます。

## 3. 承認後の適用

```sh
REVIEWED_DIGEST='承認したプレビューのdigest'
OPERATOR='担当者名または作業チケット番号'
python -m scripts.link_legacy_league apply --tournament-id 206 --expect-database "$EXPECTED_DB" --digest "$REVIEWED_DIGEST" --operator "$OPERATOR"
```

適用時は大会行をロックして候補を再計算します。ハッシュが変わっていたらエラーになり、再レビューが必要です。成功時は `action: applied` が表示されます。同じ内容の再実行は `already_applied` です。元の編成、試合ID、勝敗、ラウンド、進出情報は保持し、紐づけを別テーブルに1件記録します。

## 4. 確認と取り消し

1. プレビューを再実行して `active_digest` が承認済みの値と一致することを確認します。
2. 大会206だけ、登録段階「リーグ戦」、対戦数の下限は0または1で確認します。Win RateとDetailsでノア／トリナ／サクラ／ラプラス：アルティメットヒーロー／センチは **7戦7勝・ベスト8進出**、アニス：スター／ブラン／ビスケット／プリバティ／スノーホワイト：ヘビーアームズは **3戦3勝・ベスト16** が見込みです。段階を「全体」にした場合や大会横断の集計では、ほかの登録を含む値になります。
3. 作業前と同じ試合数、勝敗、トーナメント進行であることを確認します。投入済みの紐づけと現行の編成や試合結果が後から異なった場合、その旧試合には補正を使いません。
4. 取り消す場合は同じ大会IDとハッシュを指定します。元データは保持され、補正行だけが削除されます。その後、プレビューの `active_digest: null` と画面を確認します。

```sh
python -m scripts.link_legacy_league rollback --tournament-id 206 --expect-database "$EXPECTED_DB" --digest "$REVIEWED_DIGEST"
```

集計キャッシュは紐づけ行の追加・削除を検知するため、適用と取り消しのたびに再起動する手順はありません。
