FROM python:3.11-slim

WORKDIR /app

# システム依存ライブラリのインストール
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    tesseract-ocr-jpn \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Pythonパッケージをインストール（キャッシュ最適化のため先にrequirements.txtのみコピー）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
# （.dockerignore で不要ファイルを除外済み）
COPY . .

# uploadsディレクトリを作成（永続ボリュームのマウントポイント）
RUN mkdir -p uploads/templates uploads/cropped

EXPOSE 8000

# 起動スクリプトで DB マイグレーション実行後にサーバー起動
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
