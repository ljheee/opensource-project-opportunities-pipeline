"""Open 7606 (type hints) — unique in DB."""
import json
import sqlite3

DB = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"
conn = sqlite3.connect(DB)
cur = conn.cursor()

ev_value = {
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "peer_impl_urls": [],
    "issue_reactions": 3,
    "issue_count": 17,
    "has_workaround": False,
    "prod_signal_quote": (
        "Hey Iwan! Thanks for your interest and I'm glad you asked. Actually since "
        "going 3.7+, yes, I think the answer here has gotten a lot simpler: Type "
        "hints welcome, annotations preferred, no comments / .p"
    ),
    "has_prod_signal": False,
    "gap_desc": (
        "boltons has no type hints throughout the codebase; the maintainer is explicitly "
        "welcoming embedded annotations (not .pyi stubs) and CI-validated typing. "
        "Issue #373 was opened to confirm preferences and is open with explicit positive "
        "maintainer signal."
    ),
}
ev_diff = {
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "why_hard": (
        "Hard because: boltons is a large library with many modules; typing all of them "
        "is a multi-PR effort. Easier path: add mypy to CI and accept incremental "
        "annotated PRs per module."
    ),
    "target_approach_file": "boltons/ (entire package)",
}
ev_urg = {"cve_id": None, "has_prod_signal": False, "has_workaround": False}
ev_maint = {
    "similar_prs": [
        {
            "number": 318,
            "title": "PR #318 referenced in the issue as showing type hints are welcome",
            "merged": False,
            "url": "https://github.com/mahmoud/boltons/pull/318",
            "age_days": 1000,
            "maintainer_comment": "",
        }
    ],
    "maintainer_responses": [
        {
            "body_quote": (
                "Hey Iwan! Thanks for your interest and I'm glad you asked. Actually since "
                "going 3.7+, yes, I think the answer here has gotten a lot simpler: Type "
                "hints welcome, annotations preferred, no comments / .pyi, CI validation "
                "expected."
            ),
            "issue_number": 373,
        }
    ],
    "welcome_labels": [],
}
cur.execute(
    "UPDATE opportunities SET status='open', source_type='issue', "
    "title=?, description=?, impl_hint=?, value_evidence=?, difficulty_evidence=?, "
    "urgency_evidence=?, maintainer_evidence=?, value=NULL, difficulty=NULL, "
    "urgency=NULL, maintainer_signal=NULL WHERE id=7606",
    (
        "Add type hints (PEP 484) throughout boltons per maintainer's stated preferences",
        (
            "boltons currently has no type hints. Issue #373 confirms the maintainer's "
            "preferences: embedded annotations (not .pyi stubs), CI validation, no "
            "type comments. Maintainer explicitly welcoming, with PR #318 as reference. "
            "This is a long-running, incrementally mergeable contribution opportunity."
        ),
        (
            "Pick a single module (e.g. boltons/funcutils.py or boltons/cacheutils.py) "
            "and add type hints to public functions/classes. Use PEP 604 unions (X | None) "
            "or Optional[X] per Python 3.7+ baseline. Add a mypy.ini and a CI step that "
            "runs mypy --strict on the annotated file. Open PR per module to keep diffs "
            "reviewable. Avoid breaking the Python 2/3 compat shim if maintained."
        ),
        json.dumps(ev_value),
        json.dumps(ev_diff),
        json.dumps(ev_urg),
        json.dumps(ev_maint),
    ),
)
print("opened 7606 (type hints)")
conn.commit()

for row in cur.execute(
    "SELECT o.id, o.project_id, o.source_type, o.status, o.title FROM opportunities o "
    "WHERE o.task_id IN (1138,1139) ORDER BY o.id"
):
    print(row)
conn.close()
