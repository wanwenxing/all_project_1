"""查看 langgraph_checkpoints.db 表结构与样本数据。"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings

path = Path(settings.memory_checkpoint_path)
if not path.is_absolute():
    path = settings.back_root / path

print(f"DB: {path}")
if not path.exists():
    print("文件不存在（可能还没聊过天）")
    raise SystemExit(0)

conn = sqlite3.connect(path)
cur = conn.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("tables:", tables)
for table in tables:
    count = cur.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    print(f"\n=== {table} ({count} rows) ===")
    cols = [r[1] for r in cur.execute(f'PRAGMA table_info("{table}")')]
    print("columns:", cols)
    rows = cur.execute(f'SELECT * FROM "{table}" LIMIT 3').fetchall()
    for i, row in enumerate(rows, 1):
        print(f"--- row {i} ---")
        for col, val in zip(cols, row):
            text = val if isinstance(val, str) else repr(val)
            if len(text) > 200:
                text = text[:200] + "..."
            print(f"  {col}: {text}")
conn.close()
