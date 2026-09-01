#!/usr/bin/env python3
"""Apply judgment for task 1559 (huandu/go-sqlbuilder) - Stage 4 v2 batch.

Draft 3195 (compatibility/issue:187) duplicates existing open row 1886 (issue/issue:187).
Per Stage 4 v2 dedup UNIQUE-collision memory principle: DELETE draft, keep open row.
"""
import sqlite3

DB = "data/pipeline.db"
NOW = "2026-09-01T18:40:00+00:00"

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("DELETE FROM opportunities WHERE id=3195")
print(f"deleted 3195 (duplicate of existing open row 1886)")

cur.execute("UPDATE tasks SET status='done', finished_at=? WHERE id=1559", (NOW,))
print(f"task 1559: {cur.rowcount} row updated")
cur.execute("UPDATE projects SET status='active' WHERE id='huandu/go-sqlbuilder' AND status='analyzing'")
print(f"project huandu/go-sqlbuilder: {cur.rowcount} row updated")

conn.commit()
conn.close()
print("\n=== Task 1559 applied ===")