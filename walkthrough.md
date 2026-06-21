# 実装完了ウォークスルー

## 実装概要

既存コードを保持したまま、以下の機能をすべて差分ベースで追加・修正しました。

---

## 変更ファイル一覧

### 🔧 バックエンド（FastAPI）

| ファイル | 変更内容 |
|---------|---------|
| `backend/requirements.txt` | `python-jose`, `passlib`, `bcrypt` を追加 |
| `backend/auth.py` | **新規** JWT生成・検証・bcryptハッシュ・Depends関数 |
| `backend/models.py` | `AppUser` テーブル追加（既存テーブルは無変更） |
| `backend/main.py` | 認証エンドポイント8本追加・CORS環境変数化・upload後削除・admin保護 |
| `backend/Dockerfile` | `COPY . .` と `CMD` を追加（本番デプロイ対応） |
| `backend/.dockerignore` | **新規** `__pycache__` / `.db` / `.env` 等を除外 |

### 🖥️ フロントエンド（Next.js）

| ファイル | 変更内容 |
|---------|---------|
| `frontend/src/middleware.ts` | **新規** ルート保護（gate/login/admin への自動リダイレクト） |
| `frontend/src/app/gate/page.tsx` | サーバーサイド認証方式に修正（クライアント平文比較を廃止） |
| `frontend/src/app/secret-login/page.tsx` | `/api/auth/login` 経由に修正・Suspense対応 |
| `frontend/src/app/secret-register/page.tsx` | `/api/auth/register` 経由に修正 |
| `frontend/src/app/admin/page.tsx` | admin認証チェック追加・ユーザー管理リンク追加 |
| `frontend/src/app/admin/users/page.tsx` | **新規** ユーザー管理画面（BAN・ロール変更） |
| `frontend/Dockerfile` | マルチステージビルド（builder → runner）に変更 |
| `frontend/next.config.ts` | `BACKEND_URL` 環境変数対応（rewrite先を変更可能に） |

### 🐳 デプロイ設定

| ファイル | 変更内容 |
|---------|---------|
| `docker-compose.yml` | ローカル開発用変数整理（FIRST_ADMIN_* など追加） |
| `docker-compose.prod.yml` | **新規** 本番用（volumeなし・本番コマンド） |
| `.env.example` | **新規** 全環境変数のテンプレート |

---

## 認証の動作フロー

```
一般訪問者 → localhost:3000
  ↓ middleware が site_session Cookie を確認
  ↓ なければ
  → /gate（パスコード入力）
       ↓ POST /api/auth/gate → HttpOnly Cookie 発行
  → ダッシュボード閲覧 ✅

スタッフ → /tournaments/manage にアクセス
  ↓ middleware が auth_token Cookie を確認
  ↓ なければ
  → /secret-login（ID/PW入力）
       ↓ POST /api/auth/login → JWT Cookie 発行
  → 大会データ登録・閲覧 ✅

管理者 → /admin にアクセス
  ↓ middleware が auth_token Cookie を確認 → OK
  ↓ admin/page.tsx が /api/auth/me でroleを確認
  ↓ role !== "admin" なら /secret-login へ
  → キャラ管理・ユーザーBAN ✅
```

---

## 環境変数一覧

| 変数名 | 場所 | 説明 |
|--------|------|------|
| `DATABASE_URL` | backend | PostgreSQL接続URL |
| `SECRET_KEY` | backend | JWT署名鍵（`openssl rand -hex 32`で生成） |
| `SITE_PASSWORD` | backend | ダッシュボード閲覧パスコード（空=制限なし） |
| `INVITE_CODE` | backend | スタッフ登録招待コード（空=誰でも登録可） |
| `FIRST_ADMIN_EMAIL` | backend | 起動時に自動作成する管理者メール |
| `FIRST_ADMIN_PASSWORD` | backend | 起動時に自動作成する管理者パスワード |
| `CORS_ORIGINS` | backend | カンマ区切りの許可オリジン |
| `BACKEND_URL` | frontend | Next.js rewrites の転送先URL |

---

## ローカル動作確認

現在のローカル環境（docker-compose）で確認済み：

```
✅ POST /api/auth/gate       → 200 OK（Cookie発行）
✅ POST /api/auth/login      → 200 OK（admin@local.dev）
✅ GET  /api/auth/me         → 200 OK（JWT Cookie認証）
✅ GET  /api/auth/users      → 200 OK（admin限定）
✅ POST /api/auth/register   → 200 OK（招待コードなし=制限なし）
✅ GET  /api/admin/*（未認証）→ 401 ログインが必要です
```

---

## Railwayデプロイ手順

### 1. Railway プロジェクト作成

1. [railway.app](https://railway.app) でプロジェクト新規作成
2. **PostgreSQL** サービスを追加 → `DATABASE_URL` をコピー

### 2. バックエンドサービス

1. GitHub リポジトリを連携（または GitHub にプッシュ）
2. 「New Service」→ `./backend` フォルダを選択
3. 以下の環境変数を設定：

```env
DATABASE_URL=（RailwayのPostgreSQL URLをそのまま）
SECRET_KEY=（openssl rand -hex 32 の出力）
SITE_PASSWORD=（お好みのパスコード）
INVITE_CODE=（スタッフ招待コード）
FIRST_ADMIN_EMAIL=admin@yourdomain.com
FIRST_ADMIN_PASSWORD=（安全なパスワード）
CORS_ORIGINS=https://frontend-xxxx.up.railway.app
```

### 3. フロントエンドサービス

1. 「New Service」→ `./frontend` フォルダを選択
2. 環境変数を設定：

```env
BACKEND_URL=https://backend-xxxx.up.railway.app
```

> [!IMPORTANT]
> **CORS_ORIGINS** に必ずフロントエンドのURLを設定してください。  
> **SECRET_KEY** は必ず `openssl rand -hex 32` で生成した値を使用してください。

### 4. 初回デプロイ後

バックエンドが起動すると `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` で管理者アカウントが自動作成されます。

---

## ストレージ使用量

| 種別 | 扱い | 容量目安 |
|------|------|---------|
| スクショ原本 | OCR処理後に**即削除** | ≈ 0 MB |
| プレイヤーアイコン | uploads/cropped/ に保存 | 少量 |
| AIテンプレート画像 | uploads/templates/ に保持 | ~10-20 MB |

**Railway 5GB プランで十分に運用可能です。**
