# タスクリスト

## バックエンド
- [x] requirements.txt に認証パッケージ追加
- [x] models.py に AppUser モデル追加
- [x] auth.py 新規作成（bcrypt直接使用方式）
- [x] main.py: 認証エンドポイント追加（gate/login/logout/register/me/users/ban/role）
- [x] main.py: CORS を環境変数化
- [x] main.py: admin エンドポイントに認証 Depends 追加
- [x] main.py: upload 後にファイル削除（スクショ原本）
- [x] main.py: startup で初回 admin 自動作成
- [x] backend/Dockerfile: COPY + CMD 追加
- [x] backend/.dockerignore 新規作成
- [x] app_users テーブル: DB直接CREATE（動作確認済み）
- [x] 管理者アカウント: admin@local.dev 作成済み

## フロントエンド
- [x] middleware.ts 新規作成（ルート保護）
- [x] gate/page.tsx: サーバーサイド検証に修正 + Tailwind スタイル
- [x] secret-login/page.tsx: APIパス修正 + Suspense対応
- [x] secret-register/page.tsx: APIパス修正 + Tailwind スタイル
- [x] admin/page.tsx: 認証チェック追加
- [x] admin/users/page.tsx: ユーザー管理画面 新規作成
- [x] frontend/Dockerfile: マルチステージビルドに変更
- [x] next.config.ts: BACKEND_URL 環境変数対応

## デプロイ設定
- [x] .env.example 新規作成
- [x] docker-compose.prod.yml 新規作成
- [x] docker-compose.yml 更新（環境変数整理）

## 動作確認
- [x] POST /api/auth/gate → 200 OK
- [x] POST /api/auth/login → 200 OK（admin@local.dev）
- [x] GET /api/auth/me → 200 OK（JWT Cookie 認証）
- [x] GET /api/auth/users → 200 OK（admin限定）
- [x] POST /api/auth/register → 200 OK
- [x] GET /api/admin/all-characters（未認証） → 401 ログインが必要です
- [ ] middleware リダイレクト確認（/ → /gate）
