import sqlite3
import os
import re

db_path = "temp_current.db"  # 現在の会話DB
pattern = re.compile(b'[\x20-\x7E\xE3\x81-\x83\xE4-\xE9\x80-\xBF]{8,}')

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT idx, step_payload FROM steps WHERE step_payload LIKE '%INSERT%' OR step_payload LIKE '%POST%' ORDER BY idx ASC;")
        rows = cursor.fetchall()
        print(f"Found {len(rows)} steps referencing INSERT or POST in temp_current.db")

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
                    if "react" in text.lower() or "const " in text.lower() or "import " in text.lower():
                        continue
                    if len(text) > 8:
                        lines.append(text)
                except:
                    pass
            
            full_text = "\n".join(lines)
            if "tournaments" in full_text.lower() or "players" in full_text.lower() or "matches" in full_text.lower():
                print(f"\n========================================\nSTEP {idx}\n========================================")
                for line in lines[:30]:
                    lower_line = line.lower()
                    if "insert" in lower_line or "value" in lower_line or "select" in lower_line or "post" in lower_line or "{" in lower_line:
                        print(f"  {line[:150]}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
