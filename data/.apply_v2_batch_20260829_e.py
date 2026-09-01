#!/usr/bin/env python3
"""Apply v3 verify verdicts for batch of 20 opportunities.

Refutes:
- id=11 (triggerdotdev#1358): state=closed
- id=5725 (triggerdotdev#1566): state=closed
- id=33 (dolphinscheduler#57): meta-thread (gap_desc/issue title contains 'Who is using')

Corrected:
- id=6765 (TanStack/router#6191): reactions stored=1, actual=2 (>20% diff)

Confirmed: all remaining 16.
"""
import json, sqlite3

conn = sqlite3.connect("data/pipeline.db")
cur = conn.cursor()

# ---- Refuted (3) ----
for oid in (11, 5725, 33):
    cur.execute("UPDATE opportunities SET status='refuted' WHERE id=?", (oid,))
conn.commit()
print("refuted UPDATE rows:")
for oid in (11, 5725, 33):
    cur.execute("SELECT id, status FROM opportunities WHERE id=?", (oid,))
    print(" ", cur.fetchone())

# ---- Corrected (1) ----
# id=6765 reactions_total updated 1 -> 2 in value_evidence; issue_reactions also updated
cur.execute(
    "SELECT value_evidence, issue_reactions FROM opportunities WHERE id=6765"
)
row = cur.fetchone()
ve = json.loads(row[0]) if row[0] else {}
ve["issue_reactions"] = 2
new_ve = json.dumps(ve, ensure_ascii=False)
new_issue_reactions = 2
cur.execute(
    "UPDATE opportunities SET status='verified', value=NULL, difficulty=NULL, urgency=NULL, "
    "maintainer_signal=NULL, value_evidence=?, issue_reactions=? WHERE id=6765",
    (new_ve, new_issue_reactions),
)
conn.commit()
print("corrected UPDATE rows for id=6765:")
cur.execute("SELECT id, status, issue_reactions, value_evidence FROM opportunities WHERE id=6765")
print(" ", cur.fetchone())

# ---- Confirmed (16) ----
confirmed_ids = [10, 12, 34, 3231, 3234, 3236, 3238, 3869, 6397, 6401, 6403, 6753, 6763, 7649, 7684, 7728]
for oid in confirmed_ids:
    cur.execute("UPDATE opportunities SET status='verified' WHERE id=?", (oid,))
conn.commit()
print("confirmed UPDATE count:", cur.rowcount)
cur.execute(
    "SELECT id, status FROM opportunities WHERE id IN (10,12,34,3231,3234,3236,3238,3869,6397,6401,6403,6753,6763,7649,7684,7728)"
)
for r in cur.fetchall():
    print(" ", r)

conn.close()
print("done")