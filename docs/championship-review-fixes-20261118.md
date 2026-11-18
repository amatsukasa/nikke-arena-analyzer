# Championship設定・戦績一覧 レビュー指摘対応（2026-11-18）

## 範囲・保全

ブランチfeature/championship-arena-settings、HEAD 6f01d45579b36688dff133b19d64937019f25434のまま。既存の未コミット変更・未追跡ファイルを保持し、backend/uploadsは変更・削除・ステージしていない。commit/push/PR/merge/デプロイ/本番接続なし。新しいマイグレーション、DB更新、公開設定変更なし。既存テストは追加・変更・実行していない。

## 1. Tournament更新API

現在の関数全体では先頭のrequire_tournament_managerでdb_tournamentを取得しており、取得前参照の例外は再現する構造ではなかった。差分の一部分だけではなく現在の全体を確認した。

ただし、最初の読み取り→タイトルロック→Tournamentロックの間に別処理が関連タイトルを変更すると、古い関連情報で更新し得た。そのため次を追加した。

1. 権限確認済みTournamentからobserved_title_idを記録。
2. 現関連先と変更先のTitleをID順にロック（既存方針を維持）。
3. Tournamentをpopulate_existing + FOR UPDATE OF tournamentsで再取得。
4. 削除済みなら404。関連先がobserved_title_idと違えばrollbackして409。更新後の所有者権限も再確認する。
5. その後だけ既存の部分更新・registration_scope固定・管理者項目保護を実施。

競合時に新しいTitleを後から追加ロックして順序を崩すのではなく、再読み込みを要求する。初回取得の権限確認、名前・提供者ゲーム開始日の更新、未送信項目保持は維持。関連付け変更のchildren取得は1回にまとめ、重複SELECTを1回削減した。実際の競合実行試験・更新リクエストの書き込み確認は未実施。

## 2. 履歴を隠す設定変更

共通ensure_history_visibleを追加し、Title設定保存とTournamentのTitle付け替えの両方から使用する。OFFへの実効値遷移だけを判定し、同値保存・ONへの変更を一律には拒否しない。

| 設定をtrue→falseにする場合 | 保護対象 | 対応 |
|---|---|---|
| deck_registration_phases | ArenaDeckRegistration / ArenaMatchRevision | 409。段階ごとの編成・有効結果の参照変更を防ぐ |
| include_in_statistics | 上記＋Match＋Player経由の旧DeckSet＋TournamentSnapshot、または公開済み大会 | 409。β版旧編成/対戦結果や公開分析を隠さない |
| is_champion_arena | 同上 | 409。履歴のあるタイトルを戦績入力対象から落とさない |

保護は保守的で、未決着Matchや空のDeckSet/Snapshotでもレコードがあれば履歴として扱う。空レコードの内容から「消してよい」と推測しない。3設定の正本はChampionshipのままで、Tournamentごとの設定操作は復活させない。履歴がなければ、既存のsettings_revision検証とapply_to_existing確認を経て変更できる。確認フラグだけでは履歴保護を回避できない。

この処理は管理設定変更・関連付け変更時のみ追加の存在確認を行う。通常のトップ統計取得へ存在確認SQLを増やさない。旧形式を書き込む全経路との並行動作を含むレース検証は未実施。

## 3. Championship未関連の旧マスタ

専用ローカル受け入れDBをSET TRANSACTION READ ONLYで調査した結果：

- 未関連Tournament：0件（対象IDなし）
- そのうち旧is_champion_arena=trueの戦績入力対象：0件
- 本番の件数・ID・設定値は未確認。本番へ接続していない。

ローカル0件を理由に互換経路を省略せず、Titleが存在しない旧Tournamentのうちlegacy_is_champion_arena=trueを一覧へ追加する。

- キー：legacy-tournament:{Tournament ID}
- source：legacy_tournament、tournament_idを明示。通常Titleはchampionship:{Championship ID}。
- 表示：元の名称を保ち「旧マスタ #ID（大会タイトル未関連）」を5言語で補足。
- 同名・数値IDの一致では関連付けない。重複名称でも別IDとして保持。
- DBの関連付け・レコード統合・旧localStorage移行は行わない。
- 旧nikkeari_user_data_v1は読まず、削除/上書きもしない。新しい保存キーnikkeari_championship_results_v1は維持。

一覧APIはTitleの1 SQL＋未関連対象の1 SQLで固定2 SQL。未関連対象は必要4列だけ取得し、対象1件ごとの追加SELECTはしない。実データには対象がないため、暫定項目の表示・保存と将来の明示関連付け時のキー移行は未実機確認。将来関連付けする場合はID根拠と新保存先内の戦績衝突を別途確認する必要がある。

## 4. 日付フィールドの追跡結果

| 列 | 現行コードで確認した意味・経路 | 今回の扱い |
|---|---|---|
| Championship.date | 管理者の大会タイトル作成/編集「開催日」。個別大会作成時にTournament.dateへ継承。Titleの開催日変更APIは関連Tournament.dateを同期する既存仕様 | 戦績一覧のevent_dateへ返す。保存値は変更しない |
| Championship.start_date | 初期スキーマから存在する別の日付列。モデル/汎用API/型には残るが、現行管理モーダル・提供者画面・戦績画面には利用経路なし | dateと同一とは決めず保持。欠損dateの代用にしない。受け入れDBには非null3件あるため削除・上書きしない |
| Tournament.date | 個別大会の開催日。Titleから継承、旧未関連マスタ作成では入力日または1970-01-01が使われた | 維持。旧マスタのevent_dateが欠けても1970年を補完表示しない |
| Tournament.game_start_date | a8d4c2e6f901で追加された旧チャンアリ大会マスタの開始日。旧管理フォーム「大会の開始日（任意）」、旧戦績APIと順序フォールバックに使われた。AppUserの同名列とは別用途 | 未関連旧マスタのevent_dateにのみ使う。残存する旧管理更新APIでもこの列とdateを保存するよう修正（以前はdateだけ更新し同名列が古いまま残った） |
| Tournament.provider_game_start_date | 提供者のゲーム開始日。新規作成でAppUser.game_start_dateから省略時だけ初期化。提供者の大会情報編集とトップのゲーム開始日フィルターが使用 | 一切変更しない。戦績一覧のイベント日付や順序に流用しない |

追加の調査値：受け入れDBでChampionship.dateは非null5件、start_dateは3件、Tournament.game_start_dateは3件、provider_game_start_dateは6件。日付値を推測で更新しない。

APIの変更：/api/champion-arena/tournamentsのgame_start_dateをevent_dateへ置き換え、ArenaResultEventとArenaTournamentの型・戦績集計の並び替えを更新。新しいTitle一覧APIは未マージの機能であり、フロントと同時反映が必要。既存APIクライアントがgame_start_dateを読んでいる場合は更新が必要。管理用旧マスタAPIのgame_start_dateは旧契約として残す。

画面への影響：戦績入力画面に新しい日付表示は追加しない。戦績の「直近出場」判定は表示順→event_date→名前空間付きIDの順。Title行は従来と同じTitle.dateを使うが、フィールド名が明確になる。未関連旧マスタは旧開始日を保持して順序に利用する。提供者の日付欄とトップページのゲーム開始日フィルターは変わらない。Championship.start_dateを使う画面は新設しない。

## 5. 性能資料の確認

同梱レビュー報告書・measure-readonly.py・measurements-current/baseline.jsonと現行コードを照合した。

- トップの親通常stats useEffectはactiveTabを条件にせず、TrendsRankingsが別にtrends_result付きstatsを取得。Trendsの母数は登録済み指揮官に限定するため、一般statsを無条件に流用してはいけない。
- 全段階集計は外側と4段階の内側で更新確認SQLを繰り返す。資料の21 SQL中10回、stats先行後18 SQL中9回という値はその経路の単発計測。
- version SQLはwarmでも関連行のid/xminを走査し、Title設定の更新検出も行う。件数増加時はSQL回数だけで軽いとは判断できない。
- 主要4 APIのSQL数は基準と同じ。Trends別集計と親取得の重複は今回追加経路として分けて扱う。今回の必須修正ではこの集計仕様を広げず、性能改修は行わない。
- 同梱資料は公開1大会と内部実データ6大会の関数計測。HTTP/通信/描画/JWT/返却JSON処理を含むブラウザー表示時間でも、本番の性能保証でもない。10大会以上・複数worker・同時負荷は未確認。
- 今回確認したSQLは未関連調査と戦績一覧の読み取りのみ。戦績一覧の2 SQLを確認し、既存5タイトルがevent_date付きでスキーマ検証可能であることを確認。公開・履歴データの更新なし。

Trendsの合意済み正式版3択（初期チャンピオン対抗戦）、β版の使用者成績フィルターは変更していない。

## 確認内容・未確認

- Python AST構文、翻訳JSON構文：成功。
- フロントエンドTypeScript / Next.jsビルド：成功。builderイメージのみ作成し、アプリ再起動・環境への反映はしていない。
- git diff --check：実施。
- 既存テスト：追加・変更・実行なし。既存テストの日付fixture/旧返却値との整合は未確認。
- 更新APIへの書き込み・履歴を使う設定切替・未関連項目の実機表示・競合試験：未実施。構文/コード確認と実データの読み取り確認を、更新動作の受け入れ合格と取り違えない。

## 今回の変更ファイル

- backend/main.py
- backend/schemas.py
- backend/services/championship_settings.py
- frontend/locales/en.json
- frontend/locales/fr.json
- frontend/locales/ja.json
- frontend/locales/ko.json
- frontend/locales/zh-CN.json
- frontend/src/app/champion-arena/results/page.tsx
- frontend/src/lib/championArenaResults.ts
- docs/championship-review-fixes-20261118.md

この一覧は「本レビュー指摘に対して追加で変更した範囲」。作業開始時からあるモデル/マイグレーション/Trends/テスト等の未コミット変更と、backend/uploadsを含む未追跡ファイルはそのまま保持。既存レビュー資料を上書きせず、差分はreview-fixes-20261118/incremental-diff.txtへ保存。
