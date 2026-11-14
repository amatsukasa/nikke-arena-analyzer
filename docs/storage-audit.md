# ストレージ容量分類（読み取り専用）

本番未接続のため、実容量の数値は未取得。次のコマンドは手順であり本番で実行していない。

```sh
# 接続先と実uploadsパスを初心者向け手順Aで照合してから:
python -B scripts/audit_storage.py --root "$UPLOAD_ROOT"
```

`ICON_MIGRATION_DATABASE_URL` が必要。アプリmain/databaseはimportせず、PostgreSQLの参照SELECTは読み取り専用トランザクション。
ファイルのstatとディレクトリ走査だけを行い、画像の変換・保存・ロック作成・削除・DB更新はしない。
レポートは標準出力だけ。認証情報・個別ユーザーURLは出力しない。

| JSON分類 | 内容 | 今回の移行・削除 |
|---|---|---|
| referenced_player_png | 正規players.icon_urlが参照する正規PNG | 移行候補。バックアップ・画像検証・照合に通ったものだけ移行 |
| protected_legacy_player_png | playersからは参照されず旧deck参照があるPNG | 自動移行・削除しない |
| orphan_player_png | 正規名だが取得できたplayers/旧deck参照がないPNG | 孤立候補。削除承認ではない |
| unsupported_referenced_player_png | 所属不整合等の未対応players参照PNG | 個別調査、勝手に移行しない |
| player_webp | player_icons内のWebP | 今回のPNG変換対象外 |
| cropped | cropped配下の画像等 | 対象外。別のライフサイクル管理を維持 |
| templates | templates配下 | 対象外。認識用原本を削除しない |
| temporary_or_hidden | 隠しパス、.tmp/.bak/.recovery.json等 | 対象外。復旧記録を年齢だけで削除しない |
| other | 上記以外（debug_match、未対応名等） | 個別調査 |

カテゴリは重複しない。隠し・一時ファイル判定がtemplates/cropped等より優先される。
各分類にはfilesとbytesがあり、以下の関係になる:

- migration_candidate_bytes = referenced_player_png.bytes
- out_of_scope_bytes = その他カテゴリのbytes合計
- total_bytes = migration_candidate_bytes + out_of_scope_bytes

画像の実デコード前なので候補は「安全に移行可能な確定件数」ではない。
candidate_with_legacy_reference_countは候補のうち旧deck参照もある件数。WebPへ変換できても旧PNG削除は参照がある限り拒否される。
missing_player_reference_count/unsupported_player_urlsも確認する。

symlinks_excludedやerrorsがあればcomplete=falseで終了コード2。リンクは辿らず、読めないファイルを0bytesとして成功扱いしない。
complete=trueもDB参照の完全性・画像健全性・バックアップ検証を保証しない。欠損参照・未対応URLは別途停止条件。
この分類は取得したplayers/旧deck参照に基づく。別システムや未把握テーブルの参照が存在しないことまでは保証しない。

bytesは論理ファイルサイズ。ハードリンクはパスごとに数え、ファイルシステムの割当量・圧縮・スナップショット保持量とは異なる。
`df -h` と `du -sh` を同時点で記録する。本番データの変更中にはスナップショット整合性を保証しない。
対象外容量が大きくても、本移行ツールの対象範囲を勝手に広げない。
