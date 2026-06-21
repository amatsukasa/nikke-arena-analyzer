import sqlite3
import os

db_paths = ["temp_history.db", "temp_current.db"]

for db_path in db_paths:
    if not os.path.exists(db_path):
        continue
    print(f"\n========================================\nDATABASE: {db_path}\n========================================")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 最初の3件
        cursor.execute("SELECT idx, step_type, step_payload FROM steps ORDER BY idx ASC LIMIT 3;")
        for r in cursor.fetchall():
            idx, step_type, payload = r
            print(f"Step {idx} ({step_type}) payload length: {len(payload)}")
            # payloadのタイプ確認
            print(f"Type: {type(payload)}")
            if isinstance(payload, bytes):
                # BLOB（圧縮されているか？）
                # 先頭20バイトをヘキサで
                print(f"Bytes snippet: {payload[:50]}")
            else:
                print(f"Text snippet: {str(payload)[:100]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
