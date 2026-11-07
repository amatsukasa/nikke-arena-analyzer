# プレイヤーアイコン WebP 品質80 移行手順

この文書は本番実行を許可するものではない。各本番操作は事前承認後に実施する。
この変更の作業範囲はローカル実装・テストまで。push、PR、デプロイ、本番接続は未実施。

## 設計

- 通常大会 `seed_{seed}.webp`、champion大会 `player_{id}.webp` にBackendで正規化。
- Pillow/libwebp品質80、method=4。リサイズなし。αは可逆。入力PNG/JPEG/WebPをデコード・検証。
- 最大入力10MiB、各辺10000px、2500万画素。アニメーション、破損、未対応形式を拒否。
- フロントの切り抜きはPNGのまま。Backendが必ずWebPへ変換する。
- `players.icon_url` は正規WebP URL。DBスキーマ変更不要。
- 既存PNG参照は従来どおり配信。移行済みの旧PNG URLは権限確認後307で正規WebP URLへ転送。
- Next.jsはBackendの307を追従せず、同一オリジンの許可済みWebPパスへ転送する。
- MIMEは `image/webp` を明示。PNGという拡張子でWebP本体を返さない。
- 公開済み大会も含め、個別アイコンの閲覧は既存仕様どおり所有者・管理者限定。
- ファイル操作とDB更新は共有ファイルロック→DB行ロックの順で直列化。
- 旧PNGはアップロード時・移行時に削除しない。削除は別の承認操作。
- `PLAYER_ICON_WRITES_PAUSED=1` でアイコン登録・削除・URL更新を伴う登録処理・大会削除を503で停止。
- 通常のstale cleanupは永続アイコンを削除しない。大会削除は大会ディレクトリを両形式まとめて削除。

## ツール

`backend/scripts/migrate_player_icons.py` はアプリを起動・importせず、接続先は専用の
`ICON_MIGRATION_DATABASE_URL` 環境変数で明示する。URLや環境変数をログに出さない。
出力JSONにはプレイヤーID、画像パス、サイズ、ハッシュが含まれるため限定共有する。
DBの例外は接続情報漏洩を避けるため型のみを報告する。

共通オプション:

- `--root /app/uploads/player_icons`
- `--backup-dir /outside-volume/icon-backup-YYYYMMDD`
- `--execute` がなければdry-run（永続的なDB・ファイル変更なし）
- 実行時は `--maintenance-confirmed` が必要（verify-backupは除く）
- migrate / cleanup / rollback の実行には `--backup-export-confirmed` も必要
- migrate: `--limit 100`、`--batch-size 25` が既定。DBコミットは1画像単位。
- cleanup / rollback も --limit（既定100件）で対象を区切る。cleanupは削除済み原本をスキップして次へ進む。
- 再実行は未移行PNGを優先するため、同じコマンドで次の少量バッチへ進める。
- `--after-id N` は明示的な対象絞り込み。通常の再開に必須ではない。
- `--min-free-mib 64`、`--max-retained-mib 32` が既定。
  旧PNGとWebPが併存する分のWebP容量を最大32MiBに制限する。原本サイズ分の二重保存はしない。
  容量上限に達したら失敗としてスキップし、旧PNG削除のレビュー・承認後に再開する。
- 孤立候補のPNGは報告するだけ。自動移行・自動削除しない。
- 対応対象は `tournament_{id}/seed_{n}.png` / `player_{id}.png`。
  規約外ファイル、隠しバックアップ、旧croppedアイコンは対象外で別調査が必要。

### 本番の前提・停止条件

1. 本番のDB・Volume・デプロイコミット、全ファイル数・bytes・空き容量を確認する。
2. 別途承認したメンテナンス時間を確保する。バックアップ取得からバッチ検証完了まで
   登録操作を止め、旧版のworker・管理スクリプト・別経路の書き込みも停止する。
3. コード反映前のバックアップは、サービスの書き込み経路を外側で止めて取得する。
   反映後の追加バックアップは `PLAYER_ICON_WRITES_PAUSED=1` を全workerで有効にする。
4. 画像ロックを無視する手作業と同時実行しない。
5. `failed`、`skipped`、ハッシュ不一致、バックアップ不足、容量上限が出たら一括削除しない。
6. セッション切断・コンテナ再起動に備え、外部バックアップと最新journalを永続保管する。

### 1. DB・画像のVolume外バックアップ

Railwayの稼働コンテナ内には `railway ssh --project <ID> --environment <ID> --service <ID>` で入る。
`railway run` はローカル実行なので本番Volume調査・変換には使わない。
ここからのコマンドは接続先のLinuxシェル用。Windows PowerShellには直接貼り付けない。

`/outside-volume` は実際に準備したVolume外の保管先に読み替える。
`/app/uploads` 内にはバックアップを置かない。Railwayで別Volumeを追加する操作は不要。
一時的にコンテナの `/tmp` を使う場合、再デプロイ・再起動で失われ得るため、
必ずデプロイ前にSFTP等で管理端末／耐久性のある外部保管先へ転送する。
パスがVolume外であることに加え、`df` 等でマウント境界と空き容量も確認する。

DBは接続情報を安全に設定した `PGHOST/PGPORT/PGDATABASE/PGUSER` と認証ファイル等を使って取得:

```sh
pg_dump --format=custom --file=/outside-volume/database-before-webp.dump
```

DBバックアップはテスト用PostgreSQLへ `pg_restore` し、テーブル・件数・アイコン参照を確認する。
本番DBへ試験復元しない。画像ツールのverifyはDBバックアップ復元の代用ではない。

画像バックアップ（既存ディレクトリへの追記は拒否、新しい保管先を使う）:

```sh
python -B scripts/migrate_player_icons.py backup \
  --root /app/uploads/player_icons --backup-dir /outside-volume/icon-backup \
  --execute --maintenance-confirmed
python -B scripts/migrate_player_icons.py verify-backup \
  --root /app/uploads/player_icons --backup-dir /outside-volume/icon-backup --execute
```

backupは正規名のPNGとDBのアイコン参照スナップショットを保存する。
verify-backup --executeは全PNGをデコードし、SHA-256照合後、Volume外の一時ディレクトリへ
実際にコピーして再照合する。成功したmanifestハッシュをverified.jsonに記録する。
規約外ファイルを含むVolume全体の別バックアップも、必要に応じて取得する。

バックアップディレクトリ全体（files、manifest.json、verified.json）とDB dumpを外部へ転送し、
外部側でもハッシュと復元を検証する。これが済むまで --backup-export-confirmed を指定しない。
再デプロイでコンテナの一時領域が失われた場合、検証済みバックアップをVolume外へ戻す。
manifestやverified.jsonは手で編集しない。

### 2. WebP対応コードのデプロイと混在確認

別途レビュー・承認されたコミットを通常の手順でデプロイする。この作業ではデプロイしない。

所有者・管理者でPNG/WebP、通常大会/champion大会を確認する。第三者・未ログインの
個別アイコンは公開済み大会でも従来どおり拒否されることを確認する。
通常・championの切り抜き、登録、再登録、削除を試験データで確認する。
既存PNGはまだ消さない。メンテナンス停止は実データ移行前に再度有効化する。

### 3. dry-runと少量移行

```sh
python -B scripts/migrate_player_icons.py migrate \
  --root /app/uploads/player_icons --limit 10 --batch-size 5
python -B scripts/migrate_player_icons.py migrate \
  --root /app/uploads/player_icons --backup-dir /outside-volume/icon-backup \
  --limit 10 --batch-size 5 --execute --maintenance-confirmed --backup-export-confirmed
```

確認項目: PNGの保持、WebPのデコード・寸法・α一致、DBの正規URL、画質、
Content-Type、旧URLの307と新URLの200、権限、bytes削減、失敗件数0。
透過画像は明色・暗色背景で確認する。

実行中に原本やDBが変わった場合はスキップする。既存の異なるWebPは上書きしない。
DB更新失敗では元PNG・元URLを維持する。変換済みWebPだけが残る場合があるが、
同じ出力ハッシュであることを確認できた場合だけ、再実行でDB更新を完了できる。
DBコミット直後に停止しても、事前にfsyncしたintentと現状照合で再開可能。

### 4. 残りをバッチ移行

同じexecuteコマンドを --limit 100 --batch-size 25 などで繰り返す。
全件を指定しても空き容量・併存予算のチェックは残るが、運用上は少量ずつ確認する。
各バッチのJSONと migration.jsonl をVolume外の耐久性のある保管先へ退避する。
変換後もPNGを保持するため、275MB分の原本をもう一組Volumeへ作ることはない。
予算に達したら、次の承認付きcleanupを挟む。削除承認なしに上限値を増やさない。

### 5. 旧PNGの独立した削除

```sh
python -B scripts/migrate_player_icons.py cleanup \
  --root /app/uploads/player_icons --backup-dir /outside-volume/icon-backup
```

対象リスト・bytes、バックアップ・復元確認、WebP表示、DB未参照をレビューし、
**ユーザーから旧PNG削除の明示承認を得た後だけ**:

```sh
python -B scripts/migrate_player_icons.py cleanup \
  --root /app/uploads/player_icons --backup-dir /outside-volume/icon-backup \
  --execute --approve-delete --maintenance-confirmed --backup-export-confirmed
```

cleanupはjournalに記録された移行だけを対象とし、現在のDB参照・PNG/WebPハッシュ・
バックアップを再確認する。別プレイヤーや旧deck_sets.image_pathがPNGを参照する場合、
更新後のファイル、移行と無関係な孤立画像は削除しない。隠しバックアップも削除しない。

### 6. 全件検証と再測定

```sh
python -B scripts/migrate_player_icons.py migrate \
  --root /app/uploads/player_icons --limit 10000 --batch-size 25
```

4,748件に加えて新規登録があるならlimitを総参照数以上にする。
既存WebPもデコードして確認する。未移行・失敗・孤立候補を個別に確認する。
DB全件のURLと実ファイル、規約外画像も別途照合し、移行予定件数との差を解消する。
`df -h /app/uploads` と `du -sh /app/uploads/player_icons` を同時点で再測定。
メンテナンス解除後、新規登録・更新・両形式の表示・権限・削除を最終確認する。
journalと外部バックアップの保持期限は承認を得て決める。

## ロールバック

WebP対応コードを維持したまま、まず移行済み参照だけ戻す。
旧コードへ戻すのは、移行対象外の新規WebPが残っていないことまで確認した後に限る。

```sh
python -B scripts/migrate_player_icons.py rollback \
  --root /app/uploads/player_icons --backup-dir /outside-volume/icon-backup --limit 100
python -B scripts/migrate_player_icons.py rollback \
  --root /app/uploads/player_icons --backup-dir /outside-volume/icon-backup --limit 100 \
  --execute --maintenance-confirmed --backup-export-confirmed
```

対象は検証済みバックアップとjournalに対応し、現在も移行時のWebPであるものだけ。
旧PNGが削除済みでも外部バックアップから復元し、DBを元URL（旧クエリも含む）へ戻す。
新しいユーザーアップロードや異なるDB参照は上書きせず、手動レビューに回す。
WebPは削除しない。画像復元に必要な空き容量＋64MiBを確認する。
再実行は復旧済み参照をスキップする。複数バッチなら繰り返す。
DB更新失敗では復元PNGが残る場合があるが、元データを破壊せず再開可能。

DB全体のpg_restoreは他機能の更新も戻すため、最後の手段として別途承認・完全停止下で行う。
アプリ・DB・PNGバックアップの対応時点を揃える。手順書の文脈だけで本番DBを復元しない。

## 既知の制限

- DBとファイルシステムを単一トランザクションにはできない。意図ログ・原本保持・
  ハッシュ照合で復旧する。APIの強制終了では隠し退避ファイルが残り得るため、
  自動削除せず正規ファイルとDBを照合して個別復旧する。
- ファイルロックを無視する外部操作は完全には防げない。メンテナンスは必須。
- WebP非可逆なのでRGBは変化する。α・解像度を検証するが画質は目視確認も必要。
- 品質80・method=4の本実装は、事前比較のmethod=6と圧縮率・速度が若干異なる。
- 規約外パス・孤立画像・旧cropped画像・隠しバックアップは別調査。自動削除しない。
- migration.jsonlに書けない場合は停止する。journal失敗後はDBとintentを照合する。
- 移行中に新規アップロードされた画像は新しいバックアップなしに移行しない。

## ローカル検証記録

- 専用Docker PostgreSQL `nikke_arena_test` と一時画像・SQLiteで関連53テスト成功。
  HTTP multipart登録・配信、旧PNG互換、α一致、権限、通常/champion、削除、移行・再開・
  冪等性、DB失敗、コミット応答喪失、競合、予算超過、外部バックアップ、復旧を含む。
- Frontend `npm test`: 53件成功（プロキシのMIME・307・認証ヘッダ・不正転送拒否を含む）。
- 製品srcのみのTypeScriptチェック成功。通常の `npx tsc --noEmit --incremental false` は
  既存 `src/lib/synergyCharacters.test.ts:10` のTS5097で失敗。無関係な設定は変更していない。
- 追加の編成登録36件は35成功、1失敗。
  `test_empty_slot_is_reserved_and_not_subject_to_normal_character_lookup` は
  Character 9999がないことによるPostgreSQL外部キー違反。
  変更前HEADのmain.pyを別の一時領域から先にimportして同じ失敗を再現した。
- ブラウザでの手動トリミング・実機画質確認、本番4,748枚の変換、本番復元は未実施。
- テスト依存は `pip install -r backend/requirements-test.txt`。
  テストDBの既存安全ガードを維持し、TEST_DATABASE_URLを専用ローカルDBに設定する。

```sh
docker exec -e DATABASE_URL=sqlite+pysqlite:///:memory: \
  -e NIKKE_AUTOMATED_TEST=1 \
  -e TEST_DATABASE_URL=postgresql://postgres:password@db_test:5432/nikke_arena_test \
  nikke_arena_backend python -B -m unittest \
  tests.test_player_icon_migration tests.test_champion_player_icons_api \
  tests.test_tournament_detail_access tests.test_upload_cleanup -q
```

上記の資格情報はdocker-composeのローカル専用テストDB用で、本番の資格情報ではない。
