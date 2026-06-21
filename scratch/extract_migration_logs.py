import sqlite3
import os
import re

db_path = "temp_current.db"  # 今度は現在の会話DBを対象に
pattern = re.compile(b'[\x20-\x7E\xE3\x81-\x83\xE4-\xE9\x80-\xBF]{8,}')

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT idx, step_payload FROM steps WHERE step_payload LIKE '%migrate_sqlite%' ORDER BY idx ASC;")
        rows = cursor.fetchall()
        print(f"Found {len(rows)} steps referencing migrate_sqlite in current DB")

        for row in rows:
            idx = row[0]
            payload = row[1]
            if not isinstance(payload, bytes):
                continue
            
            matches = pattern.findall(payload)
            lines = []
            for m in matches:
                try:
                    text = m.decode('utf-8', errors='ignore').strip()
                    if len(text) > 5:
                        lines.append(text)
                except:
                    pass
            
            print(f"\n========================================\nSTEP {idx}\n========================================")
            for line in lines:
                if "react" in line.lower() or "const " in line.lower() or "import " in line.lower():
                    continue
                print(f"  {line}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
