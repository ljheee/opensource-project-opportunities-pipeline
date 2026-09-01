#!/usr/bin/env python3
"""Apply judgment for task 1558 (grpc-ecosystem/go-grpc-middleware) - Stage 4 v2 batch.

All 6 drafts are re-extractions of opportunities already represented by existing open
rows (rows 595-600 cover the same issue numbers, just with full-URL source_ref).
Per Stage 4 v2 dedup UNIQUE-collision memory principle: DELETE new drafts to avoid
duplicate coverage of the same opportunities; keep the existing open rows.
"""
import sqlite3
from datetime import datetime, timezone

DB = "data/pipeline.db"
NOW = "2026-09-01T18:35:00+00:00"

conn = sqlite3.connect(DB)
cur = conn.cursor()

draft_ids = [8846, 8847, 8848, 8849, 8850, 8851]
deleted = 0
for did in draft_ids:
    cur.execute("DELETE FROM opportunities WHERE id=?", (did,))
    deleted += cur.rowcount
print(f"deleted {deleted} drafts (all duplicates of existing open rows 595-600)")

# Mark task done
cur.execute("UPDATE tasks SET status='done', finished_at=? WHERE id=1558", (NOW,))
print(f"task 1558: {cur.rowcount} row updated")
cur.execute("UPDATE projects SET status='active' WHERE id='grpc-ecosystem/go-grpc-middleware' AND status='analyzing'")
print(f"project grpc-ecosystem/go-grpc-middleware: {cur.rowcount} row updated")

conn.commit()
conn.close()
print("\n=== Task 1558 applied ===")