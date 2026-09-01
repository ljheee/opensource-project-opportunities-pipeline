"""Apply Stage 4 v2 judgments for task 1562 (nestjs/config)."""
import sqlite3

DB = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"
TS = "2026-09-01T11:10:00+00:00"
PROJECT_ID = "nestjs/config"
TASK_ID = 1562

# All 3 drafts DELETE: 8883/8884 collide with existing open rows 4391/4393 (kept open);
# 8885 is the Renovate Dependency Dashboard — meta-discussion, hard-DELETE per principle 8.
DELETES = [8883, 8884, 8885]


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    try:
        for oid in DELETES:
            cur.execute("DELETE FROM opportunities WHERE id=?", (oid,))
            print(f"DELETE draft {oid}: {cur.rowcount} row(s)")
        cur.execute(
            "UPDATE tasks SET status='done', finished_at=? WHERE id=? AND status='analyzed'",
            (TS, TASK_ID),
        )
        print(f"task {TASK_ID}: {cur.rowcount} row(s) -> done")
        cur.execute(
            "UPDATE projects SET status='active' WHERE id=? AND status='analyzing'",
            (PROJECT_ID,),
        )
        print(f"project {PROJECT_ID}: {cur.rowcount} row(s) -> active")
        con.commit()
        print("COMMITTED")
    finally:
        con.close()


if __name__ == "__main__":
    main()