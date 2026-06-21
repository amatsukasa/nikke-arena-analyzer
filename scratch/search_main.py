import re

with open("c:/Users/youm3/.gemini/antigravity/scratch/nikke-arena-analyzer/backend/main.py", "r", encoding="utf-8") as f:
    content = f.read()

# Base.metadata.create_all や create_all, alembic, upgrade などの記述を検索
matches = []
for i, line in enumerate(content.splitlines(), 1):
    if "create_all" in line or "alembic" in line or "init_db" in line or "metadata" in line:
        matches.append((i, line))

for lno, text in matches[:100]:
    print(f"L{lno}: {text}")
