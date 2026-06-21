# 実装計画 v2 — Railway デプロイ + 認証・権限管理

## 前提：既存資産の確認結果

### すでに存在するファイル（活用する）
| ファイル | 状態 | 内容 |
|---------|------|------|
| `frontend/src/app/gate/page.tsx` | ✅ 存在 | パスコード入力UI（`NEXT_PUBLIC_SITE_PASSWORD`環境変数対応済み） |
| `frontend/src/app/secret-login/page.tsx` | ✅ 存在 | ID/PW ログインUI |
| `frontend/src/app/secret-register/page.tsx` | ✅ 存在 | 招待コード付き登録UI |
| `frontend/src/app/admin/page.tsx` | ✅ 存在 | キャラ管理UI（認証なしで誰でもアクセス可能な状態） |

### 現状の問題点
- `secret-login` は `http://localhost:5000/api/auth/login` を叩いている（Expressの旧URLが残骸として残存）
- `gate/page.tsx` は `NEXT_PUBLIC_SITE_PASSWORD` をフロントで照合（クライアント側で平文比較 → セキュリティ不十分）
- `admin/page.tsx` は誰でも `/admin` にアクセスできてしまう（認証なし）
- バックエンドに認証API（`/api/auth/login` など）が存在しない

---

## 1. ストレージ問題（Railway 5GB対策）

### 原因分析
`backend/uploads/` に以下の画像が永続蓄積される：
- `uploads/` — 登録時のスクショ原本（最大数十MB/枚）
- `uploads/templates/` — AI認識用テンプレート（小さいサイズ、管理が必要）

### 対策方針

**スクショ（原本）の即時削除**

現在の処理フロー：
```
スクショアップロード → ファイル保存 → OCR処理 → DB保存
```
改善後：
```
スクショアップロード → メモリ処理 → OCR処理 → DB保存 → ファイル削除
```

> [!IMPORTANT]
> `main.py` の `/api/tournaments/{id}/upload-image` エンドポイントで、OCR処理完了後に `os.remove(file_path)` を追加する。  
> テンプレート画像（`uploads/templates/`）は意図的に保持する（AI認識に必要）が、  
> 原本スクショ（`uploads/`直下）は処理後即座に削除する。

**テンプレートのサイズ上限管理**

- テンプレートは1キャラあたり通常1〜3枚、1枚あたり約5〜20KB
- 200キャラ × 3枚 × 20KB = **12MB** 程度（問題なし）

**Railway ボリューム設定**

- Railway は Persistent Volume（永続ストレージ）をオプションで付けられる
- 5GBプランで `uploads/templates/` のみを永続化すれば十分

---

## 2. 認証・権限管理の設計

### アクセス権限マトリクス

| ページ/機能 | 一般訪問者 | ゲートパス通過者 | 情報提供者 | 管理者 |
|------------|-----------|----------------|-----------|--------|
| `/` ダッシュボード | ❌ → `/gate` | ✅ | ✅ | ✅ |
| `/tournaments/manage` 大会登録 | ❌ | ❌ → `/secret-login` | ✅ | ✅ |
| `/tournament/[id]` 詳細・入力 | ❌ | ❌ → `/secret-login` | ✅ | ✅ |
| `/admin` キャラ管理 | ❌ | ❌ | ❌ → 403 | ✅ |

### ユーザーロール

```python
class UserRole(str, Enum):
    contributor = "contributor"  # 情報提供者
    admin = "admin"              # 管理者
```

### 認証方式

**ダッシュボード閲覧制限（ゲートパス）**

- Next.js **middleware** でセッション Cookie を確認
- `/gate` ページでパスワード入力 → サーバーサイドで検証 → Cookie 発行
- `SITE_PASSWORD` 環境変数をバックエンドで管理（フロントに漏らさない）

> [!NOTE]
> 既存の `gate/page.tsx` は `NEXT_PUBLIC_SITE_PASSWORD` で **クライアント側** 照合している。  
> これは **セキュリティ上問題あり**（パスワードがJS bundelに平文で埋め込まれる）。  
> **新方式**: `/api/auth/gate` にPOSTしてサーバーサイドで検証し、HttpOnly Cookie を発行する。

**ログインユーザー（情報提供者/管理者）**

- JWT（HttpOnly Cookie）方式
- `python-jose` + `passlib` で実装
- バックエンド FastAPI に認証エンドポイントを追加

---

## 3. 変更ファイル詳細

### 3-A. バックエンド（新規追加）

#### [NEW] `backend/auth.py`
JWT認証ユーティリティ
```
- パスワードハッシュ（bcrypt）
- JWTトークン生成・検証
- 現在ユーザー取得 依存関係
- ロール確認デコレータ
```

#### [NEW] `backend/models_auth.py`（または `models.py` に追記）
ユーザーテーブル追加
```python
class AppUser(Base):
    __tablename__ = "app_users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="contributor")  # "contributor" | "admin"
    is_banned = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
```

#### [MODIFY] `backend/main.py`
追加エンドポイント（既存コードには触れない）：
```
POST /api/auth/gate       ← サイトパスコード検証 → Cookie発行
POST /api/auth/login      ← ログイン → JWT Cookie発行
POST /api/auth/logout     ← Cookie削除
POST /api/auth/register   ← 招待コード付き登録
GET  /api/auth/me         ← 現在ユーザー情報
GET  /api/auth/users      ← ユーザー一覧（admin限定）
PUT  /api/auth/users/{id}/ban   ← BAN（admin限定）
PUT  /api/auth/users/{id}/unban ← BAN解除（admin限定）
```

既存の `/api/admin/*` `/api/characters` エンドポイントに認証 Depends を追加:
```python
# 修正前
def get_all_characters_admin(db: Session = Depends(get_db)):

# 修正後
def get_all_characters_admin(
    db: Session = Depends(get_db),
    current_user: AppUser = Depends(require_admin)  # 追加のみ
):
```

#### [NEW] `backend/alembic/versions/xxxx_add_app_users.py`
`app_users` テーブルのマイグレーション

#### [MODIFY] `backend/requirements.txt`
追加パッケージ:
```
python-jose[cryptography]
passlib[bcrypt]
```

---

### 3-B. フロントエンド

#### [MODIFY] `frontend/src/app/gate/page.tsx`
- 変更前：`NEXT_PUBLIC_SITE_PASSWORD` とクライアント側照合
- 変更後：`/api/auth/gate` にPOSTしてサーバー検証

#### [MODIFY] `frontend/src/app/secret-login/page.tsx`
- 変更前：`http://localhost:5000/api/auth/login` に直接POST
- 変更後：`/api/auth/login` にPOST（Next.js rewrites 経由）

#### [MODIFY] `frontend/src/app/secret-register/page.tsx`
- 変更前：`http://localhost:5000/api/auth/register` に直接POST
- 変更後：`/api/auth/register` にPOST（Next.js rewrites 経由）

#### [MODIFY] `frontend/src/app/admin/page.tsx`
- 認証チェックを追加（未ログイン → `/secret-login` リダイレクト）
- admin権限チェック追加（contributor → 403表示）

#### [NEW] `frontend/src/app/admin/users/page.tsx`
ユーザー管理画面（admin専用）:
- ユーザー一覧表示
- BAN / BAN解除ボタン
- ロール変更（contributor ↔ admin）

#### [MODIFY] `frontend/src/middleware.ts`
Next.js middlewareでルート保護:
```
/ → gate Cookieがなければ /gate へ
/tournaments/* → JWT Cookieがなければ /secret-login へ
/tournament/* → JWT Cookieがなければ /secret-login へ
/admin → JWT Cookieがなければ /secret-login へ（adminロール確認はサーバーで）
/gate → そのまま通す
/secret-login → そのまま通す
/secret-register → そのまま通す
```

---

### 3-C. デプロイ設定

#### [MODIFY] `backend/Dockerfile`
本番ビルド対応（コードCOPY + CMD追加）

#### [MODIFY] `frontend/Dockerfile`
マルチステージビルド（builder + runner）

#### [NEW] `docker-compose.prod.yml`
本番起動用（volumeマウントなし、本番コマンド）

#### [NEW] `.env.example`
環境変数テンプレート

#### [NEW] `backend/.dockerignore`
不要ファイル除外

---

## 4. 環境変数一覧

| 変数名 | 場所 | 説明 | 例 |
|--------|------|------|-----|
| `DATABASE_URL` | backend (実行時) | PostgreSQL接続URL | `postgresql://...` |
| `CORS_ORIGINS` | backend (実行時) | CORS許可オリジン | `https://myapp.railway.app` |
| `SECRET_KEY` | backend (実行時) | JWT署名鍵（32文字以上のランダム文字列） | `openssl rand -hex 32` |
| `SITE_PASSWORD` | backend (実行時) | ダッシュボード閲覧パスワード | `your-gate-password` |
| `INVITE_CODE` | backend (実行時) | スタッフ登録招待コード | `nikke-staff-2024` |
| `FIRST_ADMIN_EMAIL` | backend (実行時) | 初回起動時に自動作成する管理者メール | `admin@example.com` |
| `FIRST_ADMIN_PASSWORD` | backend (実行時) | 初回起動時の管理者パスワード | `secure-password` |
| `BACKEND_URL` | frontend (実行時) | Next.js rewrites 先URL | `http://backend:8000` |

> [!WARNING]
> `NEXT_PUBLIC_*` 変数は**一切使用しない**。  
> すべての認証・機密情報はサーバーサイドで処理し、ブラウザに公開しない。

---

## 5. Railwayデプロイ手順（計画）

1. `backend` を Railway の Web Service としてデプロイ
2. `frontend` を別の Railway Web Service としてデプロイ
3. Railway PostgreSQL を作成し `DATABASE_URL` を backend に設定
4. frontend の `BACKEND_URL` に backend の Railway URL を設定
5. `CORS_ORIGINS` に frontend の Railway URL を設定

---

## Open Questions（最終確認）

> [!IMPORTANT]
> **初期管理者の作成方法**: 起動時に環境変数 `FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` があれば自動作成する方式でよいですか？  
> （管理者がゼロだと誰もBAN解除できなくなるため、少なくとも1アカウントが必要です）

> [!NOTE]
> **認証セッションの有効期限**: ゲートパスCookie・JWTともに「7日間」を想定しています。変更が必要な場合はお知らせください。

> [!NOTE]
> **招待コードの運用**: 全員共通の1つのコード（環境変数 `INVITE_CODE`）を想定しています。  
> 個人単位での招待URLが必要な場合は追加設計が必要です。
