import os
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

# 親ディレクトリを sys.path に追加して、database をインポートできるようにする
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import engine

# 既存DBにテーブルだけがある場合は、このリビジョンから通常のupgradeを開始する。
# headへ直接stampすると、追加マイグレーションを未実行のまま完了扱いにしてしまうため避ける。
BASELINE_REVISION = "e8950d0bb43e"


def _get_applied_revisions():
    with engine.connect() as connection:
        return [
            row[0]
            for row in connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).fetchall()
        ]


def run_migrations():
    # プロジェクトルートの alembic.ini のパスを取得
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ini_path = os.path.join(base_dir, "alembic.ini")

    # Alembic設定を作成
    alembic_cfg = Config(ini_path)

    # 既存のテーブルを検査
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    print(f"[Migration] 現在データベースに存在するテーブル: {sorted(tables)}")

    # Alembic導入前の既存DBは、既存スキーマ相当のベースリビジョンにだけ同期する。
    required_tables = {"tournaments", "characters", "users"}
    has_required_tables = required_tables.issubset(tables)
    has_alembic_version = "alembic_version" in tables

    if has_required_tables and not has_alembic_version:
        print(
            "[Migration] 既存テーブルがありますがalembic_versionがありません。"
            f"ベースリビジョン {BASELINE_REVISION} にスタンプしてからupgradeします。"
        )
        command.stamp(alembic_cfg, BASELINE_REVISION)
    elif has_alembic_version and not _get_applied_revisions():
        print(
            "[Migration] alembic_versionが空です。"
            f"ベースリビジョン {BASELINE_REVISION} にスタンプしてからupgradeします。"
        )
        command.stamp(alembic_cfg, BASELINE_REVISION)

    # 通常のアップグレードを実行
    print("[Migration] マイグレーションの実行(upgrade head)を開始します...")
    command.upgrade(alembic_cfg, "head")
    print("[Migration] マイグレーションが完了しました。")


if __name__ == "__main__":
    run_migrations()
