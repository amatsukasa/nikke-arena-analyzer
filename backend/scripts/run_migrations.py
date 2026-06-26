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


def _repair_missing_columns():
    """Add model columns that were introduced without an Alembic migration."""
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as connection:
        inspector = inspect(connection)
        if "players" not in inspector.get_table_names():
            return
        player_columns = {
            column["name"] for column in inspector.get_columns("players")
        }
        if "icon_url" not in player_columns:
            connection.execute(text(
                'ALTER TABLE "players" '
                'ADD COLUMN IF NOT EXISTS icon_url VARCHAR'
            ))
            print("[Migration] Added players.icon_url")


def _repair_creator_foreign_keys():
    """Point creator references at the app_users table used by authentication."""
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if "app_users" not in tables:
            return

        for table in ("championships", "tournaments"):
            if table not in tables:
                continue
            columns = {column["name"] for column in inspector.get_columns(table)}
            if "created_by" not in columns:
                continue

            connection.execute(text(
                f'UPDATE "{table}" SET created_by = NULL '
                'WHERE created_by IS NOT NULL '
                'AND NOT EXISTS ('
                f'SELECT 1 FROM app_users WHERE app_users.id = "{table}".created_by'
                ')'
            ))

            has_app_user_fk = False
            for foreign_key in inspector.get_foreign_keys(table):
                if foreign_key.get("constrained_columns") != ["created_by"]:
                    continue
                if foreign_key.get("referred_table") == "app_users":
                    has_app_user_fk = True
                    continue
                constraint_name = foreign_key.get("name")
                if constraint_name:
                    connection.execute(text(
                        f'ALTER TABLE "{table}" DROP CONSTRAINT "{constraint_name}"'
                    ))

            if not has_app_user_fk:
                connection.execute(text(
                    f'ALTER TABLE "{table}" '
                    f'ADD CONSTRAINT "fk_{table}_created_by_app_users" '
                    'FOREIGN KEY (created_by) REFERENCES app_users(id)'
                ))
            print(f"[Migration] {table}.created_by now references app_users.id")


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

    # Repair schema drift before application code starts.
    _repair_missing_columns()
    _repair_creator_foreign_keys()

    # 通常のアップグレードを実行
    print("[Migration] マイグレーションの実行(upgrade head)を開始します...")
    command.upgrade(alembic_cfg, "head")
    _repair_missing_columns()
    _repair_creator_foreign_keys()
    print("[Migration] マイグレーションが完了しました。")


if __name__ == "__main__":
    run_migrations()
