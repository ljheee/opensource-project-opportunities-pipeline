"""Batch 2: remaining 5 boltons drafts (7606, 7607, 7608, 7609, 3366/3368 already done)."""
import json
import sqlite3

DB = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"
conn = sqlite3.connect(DB)
cur = conn.cursor()

# --- 7606 issue #373: Type hints ---
# Maintainer explicitly welcoming: "Type hints welcome, annotations preferred, no comments"
# PR #318 referenced. Open, maintainer engaged, clear scope. OPEN.
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

# --- 7607 performance #186: Proposal to add a few functions (large meta-proposal) ---
# This is a kitchen-sink proposal from years ago. Maintainer's response was a soft "
# "many of these look very promising". Re-classify as issue (not performance) since
# the request is to add functions, not fix performance. Open but low urgency.
# Actually the issue text and content are "add a few functions" not perf.
# Re-classify to issue type to match content.
ev_value = {
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "peer_impl_urls": [],
    "issue_reactions": 1,
    "issue_count": 20,
    "has_workaround": False,
    "prod_signal_quote": (
        "Many if not most of these look very promising! I'm kind of curious what some "
        "of them entail, and whether I can merge some with som"
    ),
    "has_prod_signal": False,
    "gap_desc": (
        "Issue #186 collects a long list of utility functions the reporter has used in "
        "their own library for 8 years and proposes adding to boltons (e.g. "
        "ioutils.input_ask_yes_no, and others). Maintainer (mahmoud) responded that "
        "many look very promising and is open to per-function PRs."
    ),
}
ev_diff = {
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "why_hard": (
        "Hard because: kitchen-sink proposal covering many small utilities; each must "
        "be evaluated, tested, and docs'd individually. No canonical reference for any "
        "specific function."
    ),
    "target_approach_file": "boltons/ioutils.py and others",
}
ev_urg = {"cve_id": None, "has_prod_signal": False, "has_workaround": False}
ev_maint = {
    "similar_prs": [
        {
            "number": 69,
            "title": "Make cache accept callable arguments, add tests.",
            "merged": False,
            "url": "https://github.com/mahmoud/boltons/pull/69",
            "age_days": 3767,
            "maintainer_comment": "",
        }
    ],
    "maintainer_responses": [
        {
            "body_quote": (
                "Hey Ben! Thanks for your patience, this issue caught me on honeymoon. "
                "Many if not most of these look very promising! I'm kind of curious what "
                "some of them entail, and whether I can merge some with som"
            ),
            "issue_number": 186,
        }
    ],
    "welcome_labels": [],
}
cur.execute(
    "UPDATE opportunities SET status='open', source_type='issue', "
    "title=?, description=?, impl_hint=?, value_evidence=?, difficulty_evidence=?, "
    "urgency_evidence=?, maintainer_evidence=?, value=NULL, difficulty=NULL, "
    "urgency=NULL, maintainer_signal=NULL WHERE id=7607",
    (
        "ioutils / others: add missing utility functions from issue #186 (e.g. input_ask_yes_no)",
        (
            "Issue #186 is a kitchen-sink proposal from a long-time user listing utility "
            "functions (e.g. ioutils.input_ask_yes_no) that they consider missing from "
            "boltons. Maintainer responded positively and invited per-function PRs. This "
            "is a multi-PR opportunity: pick one function, implement, test, docs, PR."
        ),
        (
            "Open issue #186 and pick a single, well-scoped function (e.g. "
            "ioutils.input_ask_yes_no). Look up the function in the reporter's referenced "
            "library if available, or design from the issue's description. Implement in "
            "the appropriate boltons/<topic>utils.py module. Add unit tests and a "
            "docstring with an example. Open a single-function PR referencing #186."
        ),
        json.dumps(ev_value),
        json.dumps(ev_diff),
        json.dumps(ev_urg),
        json.dumps(ev_maint),
    ),
)
print("opened 7607 (ioutils missing functions)")

# --- 7608 issue #266 dict get_all() (no maintainer engagement) ---
# Issue is still open, 18 referenced issues count, 1 reaction. Maintainer in #347
# referenced it: "If using the zip name, I'd prefer zip_dicts over dict_zip". This is
# at least a touchpoint. But the gap is just a one-line dict comprehension the user
# could use directly. No real maintainer engagement, no canonical, low value.
# DELETE — too thin to be a meaningful contribution.
cur.execute("DELETE FROM opportunities WHERE id = 7608")
print("deleted 7608 (one-liner snippet, low value)")

# --- 7609 performance #255: Python 3 style iterable defaults ---
# Maintainer explicitly said "no, no such plan at [this time]". CLEAR REFUSAL.
# DELETE.
cur.execute("DELETE FROM opportunities WHERE id = 7609")
print("deleted 7609 (maintainer explicit no)")

# --- 3369 was already deleted in batch 1 ---
# --- 3370 was already deleted in batch 1 ---
# --- 3371 was already deleted in batch 1 ---

conn.commit()
print("Batch 2 committed. Final review...")

for row in cur.execute(
    "SELECT o.id, o.project_id, o.source_type, o.status, o.title FROM opportunities o "
    "WHERE o.task_id IN (1138,1139) ORDER BY o.id"
):
    print(row)

conn.close()
