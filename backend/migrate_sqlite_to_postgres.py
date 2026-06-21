import os
import sqlite3
from sqlalchemy import create_engine, MetaData, Table, select
from sqlalchemy.orm import sessionmaker

# 接続情報
SQLITE_PATH = "nikke_arena.db"
POSTGRES_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:password@db:5432/nikke_arena")

def migrate():
    if not os.path.exists(SQLITE_PATH):
        print(f"SQLite file not found at {SQLITE_PATH}")
        return

    print("Connecting to databases...")
    # SQLite 接続
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    # PostgreSQL 接続
    pg_engine = create_engine(POSTGRES_URL)
    pg_metadata = MetaData()
    pg_metadata.reflect(bind=pg_engine)

    Session = sessionmaker(bind=pg_engine)
    pg_session = Session()

    # テーブルの移行順序 (依存関係順)
    tables = [
        "characters",
        "tournaments",
        "players",
        "deck_sets",
        "deck_teams",
        "matches",
        "round_results"
    ]

    try:
        for table_name in tables:
            print(f"Migrating table: {table_name}...")
            
            # PostgreSQLのテーブルオブジェクト取得
            pg_table = Table(table_name, pg_metadata, autoload_with=pg_engine)
            
            # 既存のデータをクリア (必要であれば)
            pg_session.execute(pg_table.delete())
            pg_session.commit()

            # SQLiteからデータ取得
            sqlite_cursor.execute(f"SELECT * FROM {table_name}")
            rows = sqlite_cursor.fetchall()
            
            if not rows:
                print(f"No rows found in SQLite table {table_name}. Skipping.")
                continue

            print(f"Found {len(rows)} rows to migrate.")
            
            # カラム一覧
            columns = rows[0].keys()
            
            # バルクインサート用のデータ作成
            insert_data = []
            for row in rows:
                row_dict = {}
                for col in columns:
                    row_dict[col] = row[col]
                insert_data.append(row_dict)
            
            # PostgreSQLへインサート
            pg_session.execute(pg_table.insert(), insert_data)
            pg_session.commit()
            print(f"Migrated {len(insert_data)} rows successfully.")

            # PostgreSQLの主キーシーケンスを更新 (IDの重複衝突を防ぐため)
            # PostgreSQLは各テーブルの自動増分IDに対してシーケンスを使っているため、
            # 直値でインサートした後はシーケンスを同期する必要があります。
            max_id_row = pg_session.execute(select(pg_table.c.id).order_by(pg_table.c.id.desc())).first()
            if max_id_row:
                max_id = max_id_row[0]
                seq_name = f"{table_name}_id_seq"
                # シーケンスが存在するか確認して更新
                try:
                    pg_session.execute(f"SELECT setval('{seq_name}', {max_id})")
                    pg_session.commit()
                    print(f"Updated sequence {seq_name} to {max_id}.")
                except Exception as seq_err:
                    pg_session.rollback()
                    # シーケンス名が異なる場合や存在しない場合はスキップ
                    print(f"Notice: Could not update sequence {seq_name} (might not exist): {seq_err}")

        print("Migration completed successfully!")

    except Exception as e:
        pg_session.rollback()
        print(f"Error occurred during migration: {e}")
    finally:
        sqlite_conn.close()
        pg_session.close()

if __name__ == "__main__":
    migrate()
