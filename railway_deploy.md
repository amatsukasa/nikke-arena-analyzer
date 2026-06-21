# Railway デプロイ手順書

## 前提条件

- GitHub にプロジェクトをプッシュ済み
- Railway アカウント作成済み（https://railway.app）

> [!NOTE]
> 各 Docker イメージのビルド済みサイズ：
> - **バックエンド**: 約1.2GB（tesseract-ocr含む）
> - **フロントエンド**: 約281MB（Next.js standalone）

---

## 全体構成

Railway に **3つのサービス** を作成します：

```
Railway プロジェクト
├── backend サービス   ← FastAPI (Python)  ← ./backend/ フォルダ
├── frontend サービス  ← Next.js (Node.js) ← ./frontend/ フォルダ
└── PostgreSQL サービス ← Railway マネージドDB
```

---

## Step 1: PostgreSQL の作成

1. Railway ダッシュボードで「**New Project**」をクリック
2. 「**Add a service**」→「**Database**」→「**Add PostgreSQL**」
3. デプロイが完了したら、PostgreSQL サービスをクリック
4. 「**Variables**」タブを開き `DATABASE_URL` の値をコピーしておく

---

## Step 2: バックエンドサービスの作成

1. 「**Add a service**」→「**GitHub Repo**」→ リポジトリを選択
2. サービスが作成されたら「**Settings**」を開く
3. **「Root Directory」を `/backend` に設定**（⬅ここが重要！）
4. 「**Build**」セクションで **「Dockerfile」** が選択されていることを確認

### 環境変数を設定（Variables タブ）

| 変数名 | 値 |
|--------|-----|
| `DATABASE_URL` | Step 1 でコピーした PostgreSQL URL |
| `SECRET_KEY` | ターミナルで `openssl rand -hex 32` を実行した結果 |
| `SITE_PASSWORD` | ダッシュボード閲覧パスコード（任意の文字列） |
| `INVITE_CODE` | スタッフ登録用招待コード（任意の文字列） |
| `FIRST_ADMIN_EMAIL` | 最初の管理者メールアドレス |
| `FIRST_ADMIN_PASSWORD` | 最初の管理者パスワード |
| `CORS_ORIGINS` | ※後で frontend の URL が確定してから設定 |
| `PORT` | `8000` |

> [!IMPORTANT]
> `CORS_ORIGINS` は frontend の Railway URL が確定してから設定します。  
> 先に backend をデプロイして URL を確認し、後で frontend の URL を追加してください。

### デプロイ確認

Railway が自動でビルド・デプロイします。  
デプロイ完了後、backend の URL（例: `https://nikke-backend-production.up.railway.app`）をメモしてください。

**ヘルスチェック:**
```
https://your-backend.up.railway.app/
→ {"message": "Welcome to NIKKE Arena Analysis API!"} が返ればOK
```

---

## Step 3: フロントエンドサービスの作成

1. 「**Add a service**」→「**GitHub Repo**」→ 同じリポジトリを選択
2. 「**Settings**」→ **「Root Directory」を `/frontend` に設定**
3. 「**Build**」セクションで **「Dockerfile」** が選択されていることを確認

### 環境変数を設定（Variables タブ）

| 変数名 | 値 |
|--------|-----|
| `BACKEND_URL` | Step 2 で確認した backend の Railway URL（例: `https://nikke-backend-xxx.up.railway.app`） |

> [!NOTE]
> `PORT` は Railway が自動設定するため、手動設定不要です。

---

## Step 4: CORS 設定の更新

frontend のデプロイが完了して URL が確定したら、backend の `CORS_ORIGINS` を更新します。

1. backend サービスの「**Variables**」を開く
2. `CORS_ORIGINS` を更新：

```
https://nikke-frontend-production.up.railway.app
```

複数のURLを許可する場合はカンマ区切り：
```
https://nikke-frontend-production.up.railway.app,http://localhost:3000
```

3. 保存すると backend が自動再デプロイされます

---

## Step 5: 初回起動確認

backend が起動すると、`FIRST_ADMIN_EMAIL` / `FIRST_ADMIN_PASSWORD` で設定した管理者アカウントが自動作成されます。

**ログイン確認:**
```
https://your-frontend.up.railway.app/secret-login
→ 上記のメールアドレス・パスワードでログイン
→ /admin ページにアクセスできれば成功
```

---

## トラブルシューティング

### ❌ 「No start command could be detected」

**原因:** Root Directory の設定が正しくない  
**解決:** Settings → Root Directory を `/backend` または `/frontend` に設定

---

### ❌ 「Cannot find module」または「ModuleNotFoundError」

**原因:** pip install が失敗している  
**解決:** Railway の「Build Logs」を確認

---

### ❌ 「relation "app_users" does not exist」

**原因:** DB マイグレーションが実行されていない  
**解決:** backend の「Deploy Logs」を確認。起動コマンドに `alembic upgrade head` が含まれているか確認

---

### ❌ フロントエンドが API に繋がらない（CORS エラー）

**原因:** `CORS_ORIGINS` に frontend の URL が含まれていない  
**解決:** Step 4 の CORS 設定更新を実施

---

### ❌ フロントエンドが白画面

**原因:** `BACKEND_URL` の設定ミス  
**解決:** backend の URL が `https://` で始まっているか確認。末尾にスラッシュが入っていないか確認

---

## ファイル構成（変更なし）

```
プロジェクトルート/
├── backend/
│   ├── Dockerfile          ← Railway がビルドに使用
│   ├── railway.json        ← Railway設定
│   ├── requirements.txt    ← Python依存パッケージ
│   ├── main.py
│   └── ...
├── frontend/
│   ├── Dockerfile          ← Railway がビルドに使用
│   ├── railway.json        ← Railway設定
│   ├── package.json
│   ├── next.config.ts
│   └── ...
└── docker-compose.yml      ← ローカル開発用（Railway不使用）
```
