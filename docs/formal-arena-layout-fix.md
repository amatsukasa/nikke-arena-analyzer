# 正式版チャンピオンアリーナ画像解析 修正報告

## A. 原因調査結果

原因は説明行追加によるROUNDタブの移動と、旧レイアウトの探索範囲制限の組み合わせ。
添付正式版の説明行はROUNDタブの上にある。顔とROUNDタブの距離が増えたわけではない。

処理経路:
- frontend/src/lib/deckImagePreparation.ts: 幅960pxの検出用canvasで白背景の連結成分を探し、元解像度からパネルを切り出す。失敗時は元画像を送信。
- 登録画面/ChampionTournamentRegistrationShell.tsx: imagesとimage_pre_croppedをmultipart送信。
- backend/main.py: champion deck/通常analyze_deckで一時アップロード保存、run_cpu_analysisからprocess_imagesを呼び、結果を返却。一時入力は削除。
- backend/services/image_processor.py: _extract_modal_roiで白パネル検出（pre_croppedなら省略）、幅1080に縦横比保持で正規化。
- _find_round_tab_anchor: HSVシアン輪郭から選択ROUNDの位置を求める。X座標でラウンド順を決める。
- _find_character_card_centers/_resolve_round_character_centers: 5つのタブの輪郭で横座標を補正。検出できない場合は既存中心座標と最大24pxの補正を使用。
- process_images: 顔領域はタブ上端+200px、160x160px。横中心から列別補正(-7,-6,-5,-2,-2)を適用。画面全体の固定座標ではなく、正規化パネルとROUNDを基準にした座標。
- template_matcher.py: グレースケール正規化とコレクションバッジをマスクした正規化相関によるテンプレート照合。外部生成AI/VLMへの送信ではない。閾値0.65。collection_classifierでバッジを別判定。
- process_imagesのsuggested_teamsを通常APIへ返却。champion経路はteams等へ整形して返却。

実測（元画像を改変せずimdecodeで読込）:

|項目|β 77625.png|正式 IMG_4397.png|
|---|---|---|
|画像解像度|1920x1080|1668x2420|
|白パネルROI x,y,w,h|782,490,498,258|233,1060,1204,723|
|正規化パネル|1080x559|1080x648|
|シアンタブ矩形 x,y,w,h|60,30,179,75|61,121,179,73|
|タブ上端/パネル高|5.37%|18.67%|
|正しい顔切り抜き上端|230|321|
|検出した5列中心|148,344,538,732,926|150,344,539,732,928|

正規化タブ位置の差は91px（正式パネル高の14.04%）。列間隔は約192～196pxでほぼ同じ。
正式版説明行はパネル内およそy=25～95px（目視概算）。カード上端もタブに追従している。
旧探索上限はβ95px/正式110px。正式版121pxのタブは範囲外だった。
修正前の正式版実測戻り値は(y=0,x=1075,reliable=False)。小さなシアン領域を採用し、顔をy=200から取得していた（正解より121px上）。
X信頼フラグは従来Y座標の使用を止めず、誤った画像も照合へ進んでいた。
リサイズ自体や後段照合の変更を原因とする証拠はなく、今回の再現原因は切り抜き基準の誤検出。

## B. 修正内容

採用: ROUNDを基準にした既存の動的座標計算を維持・修正。版識別を追加する必要はない。
- シアン探索範囲をパネル高の35%まで拡張し、既存のタブ幅・高さ・輪郭面積の信頼条件で候補を先に絞る。
- 横グリッド探索を検出したROUND行へ追従。従来のグリッドのみの補助関数呼び出しは維持。
- 読み込めない画像、有効ROUNDのない画像、顔領域が高さ内に収まらない画像はValueError。APIの既存例外経路で失敗応答となり、正常編成として返さない。
- ログは入力番号・正規化寸法・タブ座標のみ。画像本体やプレイヤー情報は記録しない。
- 既存の顔オフセット、テンプレート照合、API成功応答形式は維持。依存追加なし。追加処理は同じパネルに対するシアン輪郭検出であり、モデル等は追加しない。性能ベンチマークは未実施。

変更ファイル:
1. backend/services/image_processor.py
2. backend/tests/test_formal_arena_layout.py
3. backend/scripts/inspect_deck_crops.py
4. docs/formal-arena-layout-fix.md

β実画像のタブ位置は修正前後とも30px。βの既存補正・切り抜きサイズを維持。
信頼できない画像を従来の既定座標で処理していた挙動は、意図的に失敗へ変更。

## C. テスト結果

実行環境: ローカルPython 3.12、隔離.local/python（OpenCV 5.0.0.93）。本番DB/ストレージ接続なし。

ARENA_LAYOUT_SAMPLESに添付画像ディレクトリを設定し、以下を実行:
python -m pytest backend/tests/test_formal_arena_layout.py backend/tests/test_image_processor_modal.py backend/tests/test_template_matcher.py -q
結果: 24 passed, 50 subtests passed。
- β/正式、全5ROUND位置、720/1080/1440pxの合成パネル。
- 添付2画像それぞれ0.75/1/1.5倍の実画像リサイズ。
- 不正画像、ROUNDのない白パネルを出力生成前に拒否。
- 実画像2枚×元画像/事前切り抜き済みの計4経路でprocess_imagesを実行。5人分の160x160 PNG生成を確認。テンプレート取得を空辞書にモックし、本番の登録データを使用しない。
- 既存モーダル検出・横補正・PNG/WebP保存・テンプレート照合テスト。
- 実画像10人分の顔切り抜きと矩形重ね画像を.local/cropsへ生成し、5人横並びの顔画像を目視確認。

追加でcollection_classifierを含めた既存3スイートを実行した結果: 35 passed, 22 subtests passed、3失敗（通常テスト1件、サブテスト2件）。
原因は日本語を含む絶対パスに対するWindows OpenCV cv2.imreadの失敗。同じ既存PNGはimdecode(np.fromfile(...))では正常に読める。今回の対象外コード・fixtureは変更していない。このスイート全件成功とは報告しない。
最初のsandbox実行では一時ディレクトリ権限による失敗も発生したが、同じテストをローカル権限で再実行し解消。

未検証/限界:
- ブラウザーcanvasからAPIまでの実ブラウザーE2Eと、API/DBを含む全リポジトリテストは未実施。
- 実画像のROUND02～05、端末固有の別UI、空枠入り正式版、別言語は未提供。全ROUND位置は合成画像で検証。
- 実データのキャラクターID完全一致、コレクションレベルの実画像正解率は未検証。切り抜き修正と既存照合単体回帰の成功を確認した。
- 35%範囲を超える別レイアウトは非対応。構造が似た任意画像の完全な排除を保証するものではない。
- 不正レイアウトのValueErrorは既存API経路で500となる。成功応答にはしないが、専用422化は今回実施していない。

デバッグ生成（ローカル専用、DB/テンプレートにアクセスしない）:
python backend/scripts/inspect_deck_crops.py IMAGE --output .local/crops/example
出力: overlay.png、faces.png、face-1.png～face-5.png。画像はGit対象外で公開しない。

## D. Gitの状態

元リポジトリはfeature/player-icon-webp-optimization、未追跡backend/uploads/あり。変更・削除・checkoutは一切行っていない。
mainと保存済みorigin/mainはbb3f082。ネットワークfetchは行っておらず、リモート最新との一致は未確認。
ローカルmainを--no-hardlinksで独立cloneし、fix/formal-arena-layoutを作成。
作業先: C:/Users/youm3/Documents/にけあり/nikke-arena-analyzer-fix
論理単位のローカルコミットを1件作成（ハッシュは最終回答に記載）。git status --short --branchはブランチ名のみで、未コミット変更なし。
.local内の依存・入力測定スクリプト・デバッグ画像は未追跡の無視対象。push/PR/merge/deployなし。

## E. 本番反映に向けた注意点

- DBマイグレーション不要。既存画像・登録データの再書き込み不要。
- 本番反映前に正式版の全ROUND、空枠、対象端末の追加画像で確認。実テンプレートによる認識結果も確認する。
- デプロイ時点のmainとの差分を確認して取り込む。今回はローカルmain基準であり後続変更との統合は行っていない。
- 実稼働Python/OpenCVバージョンでも対象テストを実行する。
- 本修正はバックエンドのみで動作。ログに画像を含めない。ローカルデバッグ画像や依存ディレクトリはデプロイ対象に含めない。
- デプロイと過去画像の再解析は今回実行していない。
