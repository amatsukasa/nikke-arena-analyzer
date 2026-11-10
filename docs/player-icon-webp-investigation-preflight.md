# 本番ストレージ調査の接続前準備

2026-11-10 / feature/player-icon-webp-optimization / 元の確認HEAD c3897ed

**現在は第1段階だけ。railway login/ssh、SCP、DB照会、画像調査、バックアップはまだ実行しない。**
各段階の結果を確認してから次の1段階を案内する。この文書は本番接続の許可ではない。

## 第1段階：Windowsの道具のバージョン確認（今ここ）

目的：対応するPowerShell・CLI・Dockerがあるかだけ確認する。接続先を設定しない。
WindowsのPowerShellで次のブロックだけを実行する。バージョン表示は本番ログイン不要。

```powershell
'PowerShell: ' + $PSVersionTable.PSVersion.ToString()
railway --version
ssh -V
docker --version
```

成功：4つのバージョンが表示される。
停止：command not found、未インストール、PowerShell 7.4未満。自動インストール・ログインはしない。
共有：バージョンの4行（sshのLibreSSL補足を含めてよい）だけ。ユーザー名・端末パスを含む画面全体は送らない。
確認後はそこで止まり、結果を確認してから次の段階へ。

## 確認済み／未確認の区別

ローカル確認済み：PowerShell 7.6.9、Railway CLI 5.45.10、OpenSSH_for_Windows 9.5p2、Docker CLI 29.8.0。
Railway CLIのローカルhelpでproject/environment/service指定、SSHコマンド、identity-file、config --dry-runを確認。
これは接続成功の証明ではない。ログイン状態・SSH鍵登録・権限・本番Project/Environment/Service・SCP到達性は**未確認**。
`railway ssh config --dry-run`もRailway APIへ問い合わせ得るため、現在は実行していない。
本番接続情報、トークン、パスワード、SSH秘密鍵、環境変数一覧は取得・表示していない。

## 以降の段階（概要だけ。今は実行しない）

1. 管理画面で対象を本人が照合する：Project、Environment、バックエンドService、稼働Deployment Instance、デプロイcommit、DBサービス、Volume名とマウント先。
   同名のstaging等に注意。Service IDとService Instance IDを混同しない。識別子の実値は手元だけで記録する。
2. その後、接続許可を確認してから認証とSSH鍵・host指紋を確認する。鍵を自動登録したり、StrictHostKeyCheckingを無効化しない。
   複数replicaなら対象Instanceを明示し、SCPとSSHが同じInstanceの/tmpを扱うことを確認する。
   正式な接続方法は https://docs.railway.com/cli/ssh を参照。
3. 本番コードを変えず、レビュー済みの4ファイルだけを新規の一時領域へ転送する。
   audit_storage.py / migrate_player_icons.py / player_icons.py / database_safety.py。
   auditはmigrate内の読み取り補助関数をimportするが、main/databaseやアプリを起動せず、migrate/cleanup/rollbackを呼ばない。
   `/app`や既存uploadsへ上書きしない。転送前後のSHA-256を照合する。
   通常のSCPは同じ登録鍵を使うが、実環境の対応・認証は接続許可後に確認する。
4. 依存の有無を確認する。不足があっても稼働アプリのpip環境を更新しない。必要なら別承認で/tmp専用venvを使う。
5. DB接続先を画面に出さず、管理画面で照合した期待値とシェル内で比較する。runbook Aの非表示入力チェックはDB_TARGET_MATCHと件数だけを出す。
   Volumeは管理画面のマウントパスとfindmnt/dfを本人が照合する。別のディレクトリでも同じVolumeなら「Volume外」とは扱わない。
6. 接続先確認後に初めて、`python -B .../audit_storage.py --root 確認済みの実パス`を1回実行する。
   SELECTとstat/走査のみ。--executeオプションはない。bytecode保存は-Bで防ぐ。
   変換・削除・ロック作成・DB更新はしない。調査中は利用者の更新があり得るので、件数/容量は取得時点の観測値であり確定スナップショットではない。
7. 結果を確認して止まる。Bのバックアップは別段階。移行・削除・PRマージ・自動デプロイへ進まない。

## 調査結果の安全な共有

共有してよいもの：
- read_only / complete / total_files / total_bytes
- migration_candidate_bytes / out_of_scope_bytes
- categoriesのfiles/bytes
- missing_player_reference_count / unsupported_player_urls
- candidate_with_legacy_reference_count / symlinks_excluded / errors（既定の短い分類名のみ）
- 「対象環境・DB・Volumeを本人が照合済みか」のyes/no

共有しないもの：
- DB URL・接続ホスト・DBユーザー名・内部IP・パスワード・トークン・Cookie
- Railwayの変数画面、env/printenv、認証ログ、SSH設定/秘密鍵
- 本番画像・DB dump・manifest・journal・ユーザーID・個別画像パス
- 生の例外traceback、管理画面全体のスクリーンショット

ツールの既定JSONは集計中心だが、貼り付け前に上の項目だけになっているか本人が確認する。
エラー時は成功扱いせず、固定エラー名と終了コードだけを共有する。秘密を表示して調べない。

## バックアップ復元コマンドの事前検証結果（本番は未使用）

- 日本語・空白を含むWindows絶対パスを`--mount type=bind,...,readonly`でマウントできた。
- ダミーPNGの全画像tar展開とsha256sum照合：FULL_IMAGES_RESTORE_OK。
- 外部コピーのicon-backup検証：verified=1。
- ネットワークなしの新規PostgreSQL 15、明示PGDATA=/restore-pgdataと専用Volumeでpg_dump→Windowsへコピー→pg_restore、件数照合を確認。
- 必要なローカルイメージ：postgres:15、alpine:latest、nikke-webp-acceptance-backend。いずれもLinux/amd64。
- 本番DBの実メジャー版、pg_dump版、復元対象サイズ、/restoreのRAM容量、PCの空き容量は未確認。
- ローカルバックエンドイメージにはpg_dumpがない。runbook Bはここで止める。取得先クライアントを準備せずにバックアップ可能とは案内しない。
- 復元用コンテナは本番・既存ローカルDBのVolumeを絶対に指定しない。今回の使い捨て検証用データは実ユーザーデータではない。

本番の外部バックアップとDB/画像の実復元が未確認なら、マージ・デプロイ・移行を許可しない。
