import sys
import os
from alembic.config import Config
from alembic import command
from sqlalchemy import inspect

# 親ディレクトリを sys.path に追加して、database をインポートできるようにする
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import engine

def run_migrations():
    # プロジェクトルート의 alembic.ini のパスを取得
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ini_path = os.path.join(base_dir, "alembic.ini")
    
    # Alembic設定を作成
    alembic_cfg = Config(ini_path)
    
    # 既存のテーブルを検査
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"[Migration] 現在データベースに存在するテーブル: {tables}")
    
    # 主要テーブルが全て揃っているかチェック（壊れたDBでの誤スタンプを防ぐ）
    required_tables = {"tournaments", "characters", "users"}
    has_required_tables = required_tables.issubset(set(tables))
    has_alembic_version = "alembic_version" in tables
    
    if has_required_tables:
        if not has_alembic_version:
            print("[Migration] 主要テーブルが既に存在しますが、alembic_versionテーブルが存在しません。最新リビジョンにスタンプ（同期）します。")
            command.stamp(alembic_cfg, "head")
        else:
            # alembic_version が存在するが空の場合
            with engine.connect() as connection:
                from sqlalchemy import text
                result = connection.execute(text("SELECT * FROM alembic_version")).fetchall()
                if not result:
                    print("[Migration] 主要テーブルが存在し、alembic_versionが空です。最新リビジョンにスタンプ（同期）します。")
                    command.stamp(alembic_cfg, "head")
    
    # 通常のアップグレードを実行
    print("[Migration] マイグレーションの実行(upgrade head)を開始します...")
    command.upgrade(alembic_cfg, "head")
    print("[Migration] マイグレーションが完了しました。")

if __name__ == "__main__":
    run_migrations()
