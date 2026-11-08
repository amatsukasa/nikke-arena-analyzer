# 初心者向け：既存PNGを安全にWebPへ移行する手順

この手順は「準備・確認→人が承認→次へ」の順で使います。一括実行しないでください。
**現在は本番未確認・未実行です。本書だけを根拠にマージ／移行／削除しないでください。**
ユーザーのWebP表示・画質・アップロード受け入れは合格済みですが、本番データの復元成功とは別です。

## 最初に知っておくこと

- このプロジェクトはPRマージで自動デプロイされます。**Bのバックアップ外部退避・復元確認と書き込み停止の準備が終わる前にマージしない**でください。
- DBのテーブル追加・ALTER TABLEは不要です。移行ツールがWebPを検証した後、対象のplayers.icon_urlだけを更新します。SQLの文字列一括置換はしません。
- migrateはPNGを残します。容量回収はFの削除を別途承認してからです。
- 対象は規約どおりのplayer_icons内PNGだけです。templates、cropped、孤立PNG、隠しバックアップは勝手に削除しません。
- 以下で「Railway」は本番バックエンドのLinuxシェル、「Windows」は手元のPowerShellです。railway runは使いません。
- DB・Volume・保存先は未確認です。例のパスをコピーして確定値と見なさないでください。
- コマンドが失敗したら次へ進みません。認証情報やDB URLを画面共有・チャット・公開ログに貼らないでください。
- RailwayのSSH/SCPは[公式手順](https://docs.railway.com/cli/ssh)を参照。接続情報は管理画面の対象サービスから確認します。

## 準備カード：実環境を照合する（全段階共通）

**目的**：誤ったDB・Volume・PCフォルダーへの操作を防ぐ。
**場所**：WindowsとRailway管理画面。
**コマンド（Windows）**：

```powershell
if ($PSVersionTable.PSVersion -lt [version]'7.4') { throw 'PowerShell 7.4以上で開き直してください' }
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$Repo = 'C:\Users\youm3\.gemini\antigravity\scratch\nikke-arena-analyzer'
$Project = Read-Host '管理画面で確認した本番Project ID'
$Environment = Read-Host '管理画面で確認した本番Environment ID'
$Service = Read-Host '管理画面で確認したバックエンドService ID'
$SshTarget = Read-Host '本番バックエンドのSSHドメインまたはService Instance ID（Service IDとは別）'
$BackupDir = Read-Host '外部退避先の新規Windowsフォルダー絶対パス'
if (-not [IO.Path]::IsPathRooted($BackupDir) -or (Test-Path -LiteralPath $BackupDir)) { throw '新規の絶対パスを指定してください' }
New-Item -ItemType Directory -Path $BackupDir
railway ssh --project $Project --environment $Environment --service $Service
```

**成功表示**：選んだ本番バックエンドのLinuxプロンプト。
**停止条件**：対象が不明、権限不足、想定外のサービス、保存先の容量不足。既存フォルダーを削除して回避しない。
**確認・承認**：管理画面のProject/Environment/Service/Volume、DB名・ホスト、デプロイcommit、保存先ディスク・空き容量を人が照合して記録する。実際に使うSSH鍵は事前登録し、初回接続の指紋も確認する。

## A. 読み取り専用の現状確認

**目的**：移行対象と対象外の容量・欠損を把握する。
**場所**：Windowsでツールだけを転送、Railwayで画像・DBを読み取り。
**コマンド**：旧本番コードには新ツールがないため、PRマージせず、レビューしたツールを/tmpへ置きます。稼働アプリを置換しません。

Windows（別のPowerShell。準備カードの変数があるウィンドウを使う）：

```powershell
$ToolsTar = Join-Path $BackupDir 'reviewed-tools.tar'
tar -cf $ToolsTar -C $Repo backend/scripts/migrate_player_icons.py backend/scripts/audit_storage.py backend/services/player_icons.py backend/database_safety.py
scp $ToolsTar "${SshTarget}@ssh.railway.com:/tmp/reviewed-tools.tar"
```

Railway：

```sh
# この/tmp作業領域は新規・一時用。既存なら停止し、別の新規名でやり直す。
set -eu
WORK=$(mktemp -d /tmp/nikke-webp.XXXXXXXX) || exit 1
export WORK
mkdir "$WORK/tools"
tar -xf /tmp/reviewed-tools.tar -C "$WORK/tools"
# 運用ツールの依存確認。足りなければ停止し、技術担当者が/tmpの専用venvを用意する。
python -c 'import PIL,sqlalchemy,psycopg2; print("TOOLS_DEPENDENCIES_OK")'
# 管理画面で照合した実際のuploadsディレクトリを入力する。
printf '確認済みuploads絶対パス: '; read -r UPLOAD_ROOT
export UPLOAD_ROOT
[ -d "$UPLOAD_ROOT/player_icons" ] || { echo 'STOP: player_iconsが見つかりません'; exit 1; }
# 同じmountならVolume外とは言えません。findmntがなければdfと管理画面で技術担当者が照合。
df -h "$UPLOAD_ROOT" "$WORK"
command -v findmnt >/dev/null && findmnt -T "$UPLOAD_ROOT"
command -v findmnt >/dev/null && findmnt -T "$WORK"
# DATABASE_URLが管理画面で照合した目的のDBであることを確認してから設定。
export ICON_MIGRATION_DATABASE_URL="$DATABASE_URL"
# 表示されたDB名・ユーザー・サーバー情報を、管理画面と照合する。
PYTHONPATH="$WORK/tools/backend" python - <<'PY'
import os
from sqlalchemy import create_engine, text
from database_safety import normalize_postgresql_driver_url
engine=create_engine(normalize_postgresql_driver_url(os.environ['ICON_MIGRATION_DATABASE_URL']))
with engine.connect() as c:
    c.execute(text('SET TRANSACTION READ ONLY'))
    print('DB_IDENTITY', tuple(c.execute(text('SELECT current_database(),current_user,inet_server_addr()')).one()))
    for table in ('players','characters'):
        print(table, c.execute(text('SELECT count(*) FROM '+table)).scalar())
    print('icon_references',c.execute(text('SELECT count(*) FROM players WHERE icon_url IS NOT NULL')).scalar())
engine.dispose()
PY
python -B "$WORK/tools/backend/scripts/audit_storage.py" --root "$UPLOAD_ROOT"
```

依存不足時の技術担当者向け準備（**/tmpだけ**に追加、アプリ環境をpip更新しない）：

```sh
python -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install 'Pillow>=11.1.0,<13' sqlalchemy psycopg2-binary
# 以後のpythonをこのシェル内だけ専用venvへ切り替える。
PATH="$WORK/venv/bin:$PATH"; export PATH
```

**成功表示**：`read_only: true`, `complete: true`、categoriesの各files/bytes。対象は`migration_candidate_bytes`、対象外合計は`out_of_scope_bytes`。両者の和がtotal_bytes。
**停止条件**：接続先未照合、complete=false、errors、symlinks_excluded、欠損参照、未対応URL。容量不足や実mount不明も停止。
**確認・承認**：対象PNGの数・容量と対象外の内訳をレビュー。孤立は「消してよい」意味ではない。これは論理サイズで、ファイルシステム割当量や実削減量ではない。PNG内容のデコード・移行適否は次段階でも検証する。**監査は画像/DBに書かないが、/tmpへのツール準備は画像監査自体とは別の作業**。

## B. 本番画像とDBのバックアップ・外部退避・復元検証

**目的**：自動デプロイより前に、DBと画像を同じ時点で戻せる状態を作る。
**場所**：Railwayで書き込み停止と取得、Windowsで外部保管・使い捨てDockerへ復元。
**コマンド前の必須操作**：管理者が登録API・管理スクリプト・旧workerを含む全書き込みを外側のメンテナンスで停止し、進行中処理の完了を確認する。旧コードではPLAYER_ICON_WRITES_PAUSEDだけを信用しない。SSHシェルのexportは既存workerに伝わらない。

Railway（Aのシェルを継続）：

```sh
# pg_dumpがない場合は停止。DBバックアップ担当者の環境を先に用意する。
command -v pg_dump || { echo 'STOP: pg_dumpを準備してください'; exit 1; }
# DB URLは引数や画面へ出さず、確認済み環境変数からpg_dump専用環境へ渡す。
python - <<'PY'
import os, subprocess
from urllib.parse import urlsplit, unquote, parse_qs
u=urlsplit(os.environ['DATABASE_URL']); e=os.environ.copy()
for k,v in {'PGHOST':u.hostname,'PGPORT':str(u.port or 5432),'PGDATABASE':unquote(u.path.lstrip('/')),'PGUSER':unquote(u.username or ''),'PGPASSWORD':unquote(u.password or '')}.items(): e[k]=v
q=parse_qs(u.query)
if 'sslmode' in q: e['PGSSLMODE']=q['sslmode'][0]
subprocess.run(['pg_dump','--format=custom','--file='+os.environ['WORK']+'/database.dump'],env=e,check=True)
print('DB_DUMP_OK')
PY
# すべてのuploadsを退避。十分な/tmp空き容量がない場合はここで停止。
tar -cf "$WORK/uploads-before.tar" -C "$UPLOAD_ROOT" .
(cd "$UPLOAD_ROOT" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$WORK/uploads-files.sha256"
# 移行・復旧用のPNGバックアップも別途用意。
python -B "$WORK/tools/backend/scripts/migrate_player_icons.py" backup --root "$UPLOAD_ROOT/player_icons" --backup-dir "$WORK/icon-backup" --execute --maintenance-confirmed
python -B "$WORK/tools/backend/scripts/migrate_player_icons.py" verify-backup --root "$UPLOAD_ROOT/player_icons" --backup-dir "$WORK/icon-backup" --execute
(cd "$WORK" && sha256sum database.dump uploads-before.tar uploads-files.sha256 > transfer.sha256)
printf 'WINDOWSへ転送する実パス: %s\n' "$WORK"
```

Windows（表示された実パスを入力）：

```powershell
$RemoteWork = Read-Host 'Railwayで表示されたWORKの実パス'
scp -r "${SshTarget}@ssh.railway.com:$RemoteWork" $BackupDir
$LocalWork = Join-Path $BackupDir (Split-Path $RemoteWork -Leaf)
Get-FileHash -Algorithm SHA256 (Join-Path $LocalWork 'database.dump'),(Join-Path $LocalWork 'uploads-before.tar'),(Join-Path $LocalWork 'uploads-files.sha256')
Get-Content (Join-Path $LocalWork 'transfer.sha256')
# DBメジャーバージョンは管理画面/pg_dumpのバージョンから確認。同じか対応する新しい検証用イメージを指定。
$PgImage = Read-Host '確認済み検証用PostgreSQLイメージ（例示値でなく実際の適合版）'
$RestoreDb = 'nikke-webp-restore-' + (Get-Date -Format yyyyMMddHHmmss)
docker run -d --name $RestoreDb --network none -e POSTGRES_PASSWORD=restore-local-only -e POSTGRES_DB=restore_check $PgImage
docker exec $RestoreDb pg_isready -U postgres -d restore_check
# accepting connectionsになるまで待つ。ready前に次へ進まない。
docker cp (Join-Path $LocalWork 'database.dump') "${RestoreDb}:/tmp/database.dump"
docker exec $RestoreDb pg_restore -U postgres -d restore_check --no-owner --no-privileges --exit-on-error /tmp/database.dump
docker exec $RestoreDb psql -U postgres -d restore_check -c 'SELECT count(*) FROM players; SELECT count(*) FROM characters; SELECT count(*) FROM players WHERE icon_url IS NOT NULL;'
# 全画像を別の一時コンテナへ展開し、元ファイルの全ハッシュを検証。
docker run --rm --network none --mount "type=bind,source=$LocalWork,target=/backup,readonly" --tmpfs /restore alpine:latest sh -c 'cd /restore && tar -xf /backup/uploads-before.tar && sha256sum -c /backup/uploads-files.sha256 >/tmp/check.log && echo FULL_IMAGES_RESTORE_OK'
# アイコン用manifestもWindows側の読み取り専用コピーで再検証。イメージ名はローカルで作成した検証イメージ。
docker run --rm --network none --mount "type=bind,source=$LocalWork,target=/backup,readonly" --mount "type=bind,source=$Repo/backend,target=/code,readonly" -e PYTHONPATH=/code -e PYTHONDONTWRITEBYTECODE=1 --entrypoint python nikke-webp-acceptance-backend -B /code/scripts/migrate_player_icons.py verify-backup --root /tmp/restore-source/uploads/player_icons --backup-dir /backup/icon-backup
```

**成功表示**：DB_DUMP_OK、backed_up/verified件数一致、ファイルハッシュ一致、pg_restore終了コード0、FULL_IMAGES_RESTORE_OK、外部コピーのverified件数一致。
**停止条件**：コマンド失敗、容量不足、DB復元エラー、件数未照合、ハッシュ不一致、画像復元未確認、バックアップ場所が同じVolume、外部PCへの転送未完了。**1つでもあればC～Fは禁止**。
**確認・承認**：本番の読み取り件数と復元DBの件数が一致することを管理者が確認。バックアップがPCの耐久性のある保存先に実在し、DBと全画像の実復元が成功した証跡を保存する。認証情報や実データの公開は禁止。

## C. WebP対応コードのデプロイ（マージで自動開始）

**目的**：旧PNGを残したままWebP対応コードへ切り替える。
**場所**：Windowsで最終差分確認、GitHubでユーザーがマージ、Railway管理画面でデプロイ・全workerの停止状態確認。
**コマンド（Windows）**：

```powershell
git -C $Repo status --short --branch
git -C $Repo log -1 --oneline
git -C $Repo diff --check origin/main HEAD
```

マージ自体はGitHub画面でレビュー後にユーザーが行います。この文書は自動merge/deployしません。
**成功表示**：Railwayの対象環境にレビュー済みcommitが反映され、サービスが正常起動。
**停止条件**：Bの証跡未承認、書き込み停止未完了、レビューしたcommitと異なる、起動失敗。PNGを削除しない。
**確認・承認**：Bが完了して初めてマージ承認。新コードの全workerでPLAYER_ICON_WRITES_PAUSED=1を確認する。外側の停止も維持。再起動で/tmpが失われるため、次のD準備で実保存先を再確認する。

WindowsはPowerShell 7.4以上の同じウィンドウで作業し、nativeコマンド失敗でも停止する設定を維持します。Railwayの新しいシェルでは最初に `set -eu` を設定します。

## D. 10枚の試験移行

**目的**：実データの少量でDB参照・WebP・権限・画質を確認する。
**場所**：Windowsで外部バックアップを戻し、Railwayの新しいシェルで実行。
**コマンド**：Aの接続をやり直し、新しいWORKをmktempで作り、UPLOAD_ROOTとDB接続先を再照合する。WindowsのRemoteWorkをその新WORKへ更新し、icon-backupを転送する：

```powershell
$RemoteWork = Read-Host '再接続後に確認した新しいWORK実パス'
scp -r (Join-Path $LocalWork 'icon-backup') "${SshTarget}@ssh.railway.com:$RemoteWork/"
```

Railway（/appは実際のコード場所を確認して設定）：

```sh
cd /app
# 本番の実パス確認をやり直し、WORK/UPLOAD_ROOT/ICON_MIGRATION_DATABASE_URLを再設定済みであること。
: "${WORK:?実際の一時作業パスを設定してください}" "${UPLOAD_ROOT:?実uploadsパスを設定してください}" "${ICON_MIGRATION_DATABASE_URL:?確認済みDBを設定してください}"
python -B scripts/migrate_player_icons.py verify-backup --root "$UPLOAD_ROOT/player_icons" --backup-dir "$WORK/icon-backup" --execute
python -B scripts/migrate_player_icons.py migrate --root "$UPLOAD_ROOT/player_icons" --limit 10 --batch-size 5 --after-id 0
# dry-runの10候補を承認した場合だけ実行。JSON内のURL・IDは限定共有。
python -B scripts/migrate_player_icons.py migrate --root "$UPLOAD_ROOT/player_icons" --backup-dir "$WORK/icon-backup" --limit 10 --batch-size 5 --after-id 0 --execute --maintenance-confirmed --backup-export-confirmed
```

**成功表示**：failed=0、successが実処理件数、next_after_idが次ページ開始用ID。正常WebP済みはalready_webpに計上される。
**停止条件**：failed、stopped_for_capacity、ハッシュ不一致、画像/DB表示異常。終了コードだけで判断しない。
**確認・承認**：PNG保持・DBの正規URL・WebP寸法/α・MIME・旧URL307/新URL200・権限・画質を10件で確認。全件がWebP済みの場合は新規移行成功とは数えない。確認後にEを承認。JSONと最新journalをPCへ退避。

## E. 残りの段階的移行

**目的**：先頭の失敗候補で詰まらず、全ページを確認する。
**場所**：Railway。バッチ後の保存はWindows。
**コマンド**：`AFTER_ID`には直前の出力`next_after_id`を入力します。推測したIDは使いません。

```sh
printf '直前のnext_after_id: '; read -r AFTER_ID
python -B scripts/migrate_player_icons.py migrate --root "$UPLOAD_ROOT/player_icons" --backup-dir "$WORK/icon-backup" --limit 100 --batch-size 25 --after-id "$AFTER_ID" --execute --maintenance-confirmed --backup-export-confirmed
```

Windowsで各バッチ後、最新記録を退避（同じicon-backupフォルダーに反映されることを確認）：

```powershell
scp "${SshTarget}@ssh.railway.com:$RemoteWork/icon-backup/migration.jsonl" (Join-Path $LocalWork 'icon-backup/migration.jsonl')
```

**成功表示**：failed=0。exhausted=trueで「この走査の末尾」であり、過去の失敗解決を意味しない。
**停止条件**：失敗は未解決一覧へ記録し自動で次へ進まない。原因をレビューし、後続を進めると明示判断した場合だけ返されたカーソルを使う。容量停止ではカーソルは失敗画像の手前のまま。容量対策後に同じカーソルから再試行し、飛ばさない。
**確認・承認**：各バッチの成功/失敗/既存WebP件数を記録。失敗対象は原因修正後にafter-id=0から再走査する。途中で新たなアップロードが発生したら停止し、バックアップ対象と再開位置を再評価。単に同じコマンドを連打しない。

## F. 古いPNGの承認付き削除

**目的**：移行済みで未参照の原本だけを消し、容量を回収する。
**場所**：Railway。承認記録と外部退避はWindows。
**コマンド**：最初は削除しない確認。最初のafter-sourceは空文字。

```sh
AFTER_SOURCE=''
python -B scripts/migrate_player_icons.py cleanup --root "$UPLOAD_ROOT/player_icons" --backup-dir "$WORK/icon-backup" --limit 100 --after-source "$AFTER_SOURCE"
# 対象リスト・外部バックアップ・復元・最新journalを確認し、削除を明示承認した場合だけ:
python -B scripts/migrate_player_icons.py cleanup --root "$UPLOAD_ROOT/player_icons" --backup-dir "$WORK/icon-backup" --limit 100 --after-source "$AFTER_SOURCE" --execute --approve-delete --maintenance-confirmed --backup-export-confirmed
```

**成功表示**：itemsのstatus=deleted、skipped=0。次は出力next_after_sourceをAFTER_SOURCEに設定し、毎ページdry-run→承認→execute。辞書順のパスなのでID数字の大小から推測しない。
**停止条件**：skipped、参照あり、バックアップ不足、ハッシュ変更。既存ファイルを手作業で削除しない。先頭が全skipでもレビュー承認後にnext_after_sourceで後続へ進めるが、skipした画像は残す。
**確認・承認**：削除承認は移行承認と別。権限・DB参照・復元可能性・対象bytesを確認。空き容量と併存予算でEとFを交互にする場合、新しく移行したパスが過去のcleanupカーソルより前にあり得るため、**新しいcleanup走査は必ず空文字から**。exhausted=trueでも未解決skipを廃棄しない。

## G. 完了確認と復旧方法

**目的**：全参照・容量・未解決項目を確認し、安全に再開する。問題時は画像を確保してから参照を戻す。
**場所**：Railway。証跡保管はWindows。
**コマンド（完了確認）**：

```sh
python -B scripts/audit_storage.py --root "$UPLOAD_ROOT"
python -B scripts/migrate_player_icons.py migrate --root "$UPLOAD_ROOT/player_icons" --limit 100 --after-id 0
# 出力next_after_idで全ページのdry-runを行う。最初の100件だけで全件完了としない。
df -h "$UPLOAD_ROOT"
du -sh "$UPLOAD_ROOT/player_icons"
```

**成功表示**：complete=true、対象/対象外容量の整合、全ページのfailed=0、未移行・未解決リストが説明済み。WebPの表示・新規登録・更新をメンテナンス解除後に確認。
**停止条件**：欠損・不整合・未解決skip・journal紛失。未解決を「件数が減ったから成功」としない。
**確認・承認**：書き込み停止解除とバックアップ保持期間を管理者が承認。過去のPNGを消した後も外部バックアップを保持する。

**復旧時の目的**：変更されていない移行対象だけ、PNG実体を復元して元URLへ戻す。
**場所**：Railway（書き込み停止・外部バックアップとjournal再照合後）。
**コマンド**：

```sh
AFTER_ID=0
python -B scripts/migrate_player_icons.py rollback --root "$UPLOAD_ROOT/player_icons" --backup-dir "$WORK/icon-backup" --limit 100 --after-id "$AFTER_ID"
# 復旧候補を承認した場合だけ:
python -B scripts/migrate_player_icons.py rollback --root "$UPLOAD_ROOT/player_icons" --backup-dir "$WORK/icon-backup" --limit 100 --after-id "$AFTER_ID" --execute --maintenance-confirmed --backup-export-confirmed
```

**成功表示**：status=restored、skipped=0。出力next_after_idで次のページへ。復元PNG1枚分＋64MiBの空き容量が必要。
**停止条件**：新しいアップロード・所属変更・画像ハッシュ変更・空き容量不足・journal不足はスキップして人が確認。WebPは削除しない。
**確認・承認**：先頭が復旧不能でも、記録を保存し後続の復旧を承認した場合だけカーソルを進める。DB全体のpg_restoreは通常の復旧ではなく別途承認する障害対応。旧アプリへ戻すだけでは新規WebPを読めなくなる可能性がある。

## 判定用メモ

- カーソルは「検査した位置」で、バックアップ・安全性・完了の証明ではありません。
- migrate/rollbackはID昇順、cleanupは原本パスの辞書順。モードごとのカーソルを混ぜない。
- cleanup/rollbackのCLI出力は従来の配列ではなく、items/processed/skipped/exhausted/next_after_*を持つJSONになっています。
- dry-runはカーソルをファイルへ保存しません。出力は操作者が外部記録し、次の値を明示指定します。
- 操作が中断したら、最後の出力だけを信用せず最新journalとDB/ファイルを再照合。分からなければ先頭からdry-runします。
- 実際のDB/Volume/保存先・メンテナンス停止方法・復元検証結果は未確認です。本番への導入判断はこれらを埋めてからです。
