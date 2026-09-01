#!/usr/bin/env python3
"""Apply Stage 4 v2 batch judgment for task 1442 (cloudwego/hertz)."""
import sqlite3
from datetime import datetime, timezone

DB = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"
NOW = datetime.now(timezone.utc).isoformat()

con = sqlite3.connect(DB)
cur = con.cursor()


def delete_draft(opp_id):
    cur.execute("DELETE FROM opportunities WHERE id=? AND status='draft'", (opp_id,))


def done_task(task_id, project_id):
    cur.execute("UPDATE tasks SET status='done', finished_at=? WHERE id=?",
                (NOW, task_id))
    cur.execute("UPDATE projects SET status='active' WHERE id=? AND status='analyzing'",
                (project_id,))


print("=== Task 1442: cloudwego/hertz ===")

# feature_gap false positives (blacklist: project structure / monorepo submodules / docs)
delete_draft(8406)
print("  8406 -> DELETE (.idea config dir, blacklist)")
delete_draft(8407)
print("  8407 -> DELETE (buildSrc build artifact dir, blacklist)")
delete_draft(8408)
print("  8408 -> DELETE (framework-api module split, blacklist)")
delete_draft(8409)
print("  8409 -> DELETE (framework-bom module split, blacklist)")
delete_draft(8410)
print("  8410 -> DELETE (framework-docs module split, blacklist)")

# issue/compatibility duplicates with already-open opps
delete_draft(8412)
print("  8412 -> DELETE (duplicate of open opp 5004)")
delete_draft(8413)
print("  8413 -> DELETE (duplicate of open opp 5005)")
delete_draft(8415)
print("  8415 -> DELETE (duplicate of open opp 547)")
delete_draft(8411)
print("  8411 -> DELETE (duplicate of open opp 543)")
delete_draft(5007)
print("  5007 -> DELETE (duplicate of open opp 546)")

done_task(1442, "cloudwego/hertz")
print("  Task 1442 -> done")

con.commit()
print("\nCommitted task 1442 changes.")