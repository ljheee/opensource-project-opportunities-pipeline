"""Apply Stage 4 v2 judgments for task 1561 (mher/flower)."""
import json
import sqlite3

DB = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"
TS = "2026-09-01T11:05:00+00:00"
PROJECT_ID = "mher/flower"
TASK_ID = 1561

# 6 drafts to promote; 4 drafts to delete (UNIQUE collisions with existing open rows
# 6341 issue:770, 6342 issue:895, 6343 issue:1357, 6346 issue:1322).
DELETES = [8864, 8865, 8866, 8869]

UPDATES = [
    # 6340 — issue:1348 Option to retry a failed task (20 reactions, very popular feature)
    dict(
        oid=6340,
        source_ref="issue:1348",
        source_type="issue",
        title="Add option to manually retry a failed task from the Flower UI",
        description=(
            "Flower currently has no way to manually re-queue a failed task from the UI. "
            "Users with 100+ reaction votes ask for a per-task 'Retry' action that re-publishes "
            "the task to Celery with the original args. Implement a retry button that calls "
            "the existing task.retry() Celery API."
        ),
        impl_hint=(
            "Locate the task details page template (likely under flower/templates/tasks.html). "
            "Add a 'Retry' button that POSTs to a new endpoint (e.g. /task/<id>/retry). The "
            "endpoint should fetch the AsyncResult, call task.retry(), and return the new task "
            "id. Wire up the URL route in the flower/ui blueprint."
        ),
        value_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 20,
            "issue_count": 29,
            "has_workaround": False,
            "prod_signal_quote": "",
            "has_prod_signal": False,
            "gap_desc": "Flower has no UI affordance to retry a failed task, forcing operators to the Celery CLI",
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: requires wiring a new POST endpoint, serialising task args "
                "back to the wire format, and ensuring the original task queue is still bound"
            ),
            "target_approach_file": "flower/ui/ (templates + view)",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": False, "has_workaround": False},
        maintainer_evidence={
            "similar_prs": [
                {
                    "number": 724,
                    "title": "Option to store events inside a Postgres database",
                    "merged": False,
                    "url": "https://github.com/mher/flower/pull/724",
                    "age_days": 3325,
                    "maintainer_comment": "",
                },
            ],
            "maintainer_responses": [],
            "welcome_labels": [],
        },
    ),
    # 6344 — issue:1189 Delete Tasks Older than a specified time
    dict(
        oid=6344,
        source_ref="issue:1189",
        source_type="issue",
        title="Add task-cleanup commands (delete tasks older than T / delete all)",
        description=(
            "Operators using Flower in production accumulate huge task result sets that slow "
            "the dashboard. Add CLI/API to purge tasks older than a configurable age, or all "
            "tasks, backed by a configurable periodic job."
        ),
        impl_hint=(
            "Add two new endpoints to the Flower API: /api/tasks/cleanup?older_than=<seconds> "
            "and /api/tasks/clear (admin-protected). Both should iterate the celery result "
            "backend (Redis or DB) and call result.forget(). Add CLI flags --purge-tasks and "
            "--max-task-age for the same operations in flower --purge-on-start."
        ),
        value_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 5,
            "issue_count": 31,
            "has_workaround": False,
            "prod_signal_quote": "",
            "has_prod_signal": False,
            "gap_desc": "Flower has no task-cleanup API, forcing operators to drop result-store keys manually",
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: requires understanding Celery's result backend abstraction "
                "and respecting per-result-backend semantics (Redis vs DB vs S3)"
            ),
            "target_approach_file": "flower/api/ (new endpoints) and flower/command.py (CLI flags)",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": False, "has_workaround": False},
        maintainer_evidence={"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
    ),
    # 6345 — issue:1294 Queues column on Brokers tab (small UI improvement)
    dict(
        oid=6345,
        source_ref="issue:1294",
        source_type="issue",
        title="Add a Queues column to the Brokers tab listing each broker's known queues",
        description=(
            "The Brokers tab shows broker URL and stats but not which queues are bound to "
            "each broker. Add a 'Queues' column (or expandable row) listing the queue names "
            "visible to the connected Celery worker(s)."
        ),
        impl_hint=(
            "Locate the Brokers template (flower/templates/broker.html or similar). Add a "
            "column that calls a new backend method to enumerate queues via celery.app.amqp "
            "or by introspecting the broker connection. Cache the result for 30s to avoid "
            "scanning every render."
        ),
        value_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 4,
            "issue_count": 7,
            "has_workaround": False,
            "prod_signal_quote": "",
            "has_prod_signal": False,
            "gap_desc": "Brokers tab lacks visibility into the queues bound to each broker",
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: Celery's queue enumeration differs per broker transport; "
                "needs broker-agnostic abstraction with broker-specific implementations"
            ),
            "target_approach_file": "flower/views.py or flower/api/broker.py",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": False, "has_workaround": False},
        maintainer_evidence={"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
    ),
    # 6347 — perf 771 100% CPU
    dict(
        oid=6347,
        source_ref="issue:771",
        source_type="performance",
        title="Investigate and fix 100% CPU usage reported in Celery-Flower 0.9.2",
        description=(
            "Several users report Flower consuming 100% CPU until SIGKILLed. Maintainer "
            "suggested PR #1111 was the likely cause. Reproduce the workload on current "
            "master and confirm the regression is fixed; otherwise profile and identify the "
            "hot loop (likely the events consumer)."
        ),
        impl_hint=(
            "git log --oneline -- flower/events/events.py to trace the consumer loop. Add a "
            "pprof HTTP endpoint guarded by a config flag and profile under a synthetic "
            "workload of 10k tasks/min. Compare CPU between the offending and current "
            "versions; identify and fix the hot path."
        ),
        value_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 2,
            "issue_count": 27,
            "has_workaround": False,
            "prod_signal_quote": (
                "celery-flower needed to be SIGKILLed after running at 100% CPU"
            ),
            "has_prod_signal": True,
            "gap_desc": (
                "Flower can spin at 100% CPU under specific workloads, blocking operators "
                "from deploying it to production"
            ),
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: requires reproducing the load profile, profiling the events "
                "loop, and fixing whichever tight loop is misbehaving — depends on the "
                "specific PR #1111 regression"
            ),
            "target_approach_file": "flower/events/events.py",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
        maintainer_evidence={
            "similar_prs": [],
            "maintainer_responses": [
                {
                    "author_association": "MAINTAINER",
                    "body_quote": "https://github.com/mher/flower/pull/1111 can cause the cpu increase. Please try the latest master version",
                    "issue_number": 771,
                },
            ],
            "welcome_labels": [],
        },
    ),
    # 8870 — issue 729 Retries counter bug
    dict(
        oid=8870,
        source_ref="issue:729",
        source_type="issue",
        title="Fix incorrect Retries counter on Flower dashboard",
        description=(
            "The Retries counter on the main menu and Retried tab appears to be miscounting: "
            "users report it shows values inconsistent with the actual Celery task metadata. "
            "Audit the retry counting logic and align with Celery's authoritative retry count."
        ),
        impl_hint=(
            "Find the retry-count computation in flower/events/events.py or "
            "flower/views/handlers.py. Cross-check against celery.app.task.AsyncResult.retries. "
            "Add unit tests that construct tasks with known retries=0/1/2 and assert the "
            "counter reflects the truth."
        ),
        value_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 3,
            "issue_count": 15,
            "has_workaround": False,
            "prod_signal_quote": "",
            "has_prod_signal": False,
            "gap_desc": "Flower's Retries counter is miscounting in the main menu and Retried tab",
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: retry metadata is stored across the task body and Celery "
                "result backend; needs careful unification"
            ),
            "target_approach_file": "flower/events/events.py (approx)",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": False, "has_workaround": False},
        maintainer_evidence={"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
    ),
    # 8871 — issue 626 Repeated KeyError
    dict(
        oid=8871,
        source_ref="issue:626",
        source_type="issue",
        title="Fix repeated KeyError exceptions raised from Flower when handling tasks",
        description=(
            "Users report repeated KeyError exceptions in flower logs, often from "
            "worker/task state lookups. Trace the exception path, identify the missing "
            "key, and add a guard or fix the upstream query."
        ),
        impl_hint=(
            "Run flower under a synthetic task workload with debug logging enabled. The "
            "KeyError is likely a dict-key access in flower/views/handlers.py or "
            "flower/events/events.py. Add EAFP with .get() / explicit None checks; add a "
            "test that asserts no exceptions on the workload."
        ),
        value_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 3,
            "issue_count": 30,
            "has_workaround": False,
            "prod_signal_quote": "",
            "has_prod_signal": False,
            "gap_desc": "Flower raises KeyError exceptions intermittently when handling tasks",
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: tracing the KeyError requires reproducing the missing key; "
                "the fix is local but the diagnosis spans Celery state transitions"
            ),
            "target_approach_file": "flower/views/handlers.py (approx)",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": False, "has_workaround": False},
        maintainer_evidence={"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
    ),
]


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    try:
        for oid in DELETES:
            cur.execute("DELETE FROM opportunities WHERE id=?", (oid,))
            print(f"DELETE draft {oid}: {cur.rowcount} row(s) (UNIQUE collision with existing open row)")
        for u in UPDATES:
            cur.execute(
                """SELECT id, status FROM opportunities
                   WHERE project_id=? AND source_type=? AND source_ref=? AND id<>?""",
                (PROJECT_ID, u["source_type"], u["source_ref"], u["oid"]),
            )
            collision = cur.fetchone()
            if collision:
                cur.execute("DELETE FROM opportunities WHERE id=?", (u["oid"],))
                print(
                    f"DELETE draft {u['oid']} (collides with existing row {collision[0]} "
                    f"status={collision[1]} on {u['source_type']}/{u['source_ref']})"
                )
                continue
            cur.execute(
                """UPDATE opportunities
                   SET status='open', source_type=?, title=?, description=?, impl_hint=?,
                       value_evidence=?, difficulty_evidence=?, urgency_evidence=?, maintainer_evidence=?,
                       value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
                   WHERE id=?""",
                (
                    u["source_type"],
                    u["title"],
                    u["description"],
                    u["impl_hint"],
                    json.dumps(u["value_evidence"], ensure_ascii=False),
                    json.dumps(u["difficulty_evidence"], ensure_ascii=False),
                    json.dumps(u["urgency_evidence"], ensure_ascii=False),
                    json.dumps(u["maintainer_evidence"], ensure_ascii=False),
                    u["oid"],
                ),
            )
            print(f"UPDATE {u['oid']}: {cur.rowcount} row(s) -> open/{u['source_type']}")
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