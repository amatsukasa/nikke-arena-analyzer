import sqlite3
import os
import re

db_path = "temp_history.db"

pattern = re.compile(b'[\x20-\x7E\xE3\x81-\x83\xE4-\xE9\x80-\xBF]{8,}')

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # idx が 350〜390 のステップを取得
        cursor.execute("SELECT idx, step_payload FROM steps WHERE idx >= 350 AND idx <= 390 ORDER BY idx ASC;")
        rows = cursor.fetchall()
        print(f"Scanning steps 350-390 (Count: {len(rows)})")

        for row in rows:
            idx = row[0]
            payload = row[1]
            if not isinstance(payload, bytes):
                continue
            
            # デコードされたテキスト一覧
            matches = pattern.findall(payload)
            lines = []
            for m in matches:
                try:
                    text = m.decode('utf-8', errors='ignore').strip()
                    if len(text) > 5:
                        lines.append(text)
                except:
                    pass
            
            full_text = "\n".join(lines)
            if "migrate" in full_text.lower() or "python" in full_text.lower() or "sqlite" in full_text.lower():
                print(f"\n========================================\nSTEP {idx}\n========================================")
                # 関連する行を出力
                for line in lines:
                    if "react" in line.lower() or "const " in line.lower() or "import " in line.lower():
                        continue
                    print(f"  {line}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
