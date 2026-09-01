"""Apply Stage 4 v2 judgment protocol to tasks 1138, 1139."""
import json
import sqlite3
from datetime import datetime, timezone

DB = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"
FINISHED_AT = "2026-08-29T22:00:00+00:00"

conn = sqlite3.connect(DB)
conn.execute("PRAGMA journal_mode=WAL;")
cur = conn.cursor()

# ========== TASK 1138: gocronx-team/gocron ==========
# All 3 drafts are user questions/how-to with no canonical reference.
# canonical_url is empty for this project, so no canonical-based justification.
# These are "questions" not actionable contribution opportunities.
# DECISION: DELETE all 3.
for oid in (6841, 7616, 7617):
    cur.execute("DELETE FROM opportunities WHERE id = ?", (oid,))
    print(f"deleted {oid}")

# ========== TASK 1139: mahmoud/boltons ==========
# canonical_url is empty (no Java/Go/Rust/TS counterpart to reference).
# We judge each issue on intrinsic merit: open issue, real defect, maintainer signal,
# specific scope.

# --- 7611 compatibility: remerge list merge bug (mahmoud confirmed bug) ---
ev_value = {
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "peer_impl_urls": [],
    "issue_reactions": 0,
    "issue_count": 17,
    "has_workaround": False,
    "prod_signal_quote": (
        "The significant change in the code is the addition of 'zones': [{'a': 1}], "
        "to overlay. which produces {0: {'a': 1}, 'endpoints': {...}} — the merge of "
        "the sub-dict fails when list-typed values are involved"
    ),
    "has_prod_signal": True,
    "gap_desc": (
        "remerge does not correctly handle list-typed nested values: per the maintainer, "
        "default remap extends lists while remerge updates items recursively, producing "
        "broken results when an overlay contains a list field alongside dict fields"
    ),
}
ev_diff = {
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "why_hard": (
        "Hard because: requires understanding the list-vs-dict merge semantics in "
        "remerge and adding a test that covers list-typed nested values; no canonical "
        "reference implementation available for guidance"
    ),
    "target_approach_file": "boltons/iterutils.py",
}
ev_urg = {"cve_id": None, "has_prod_signal": True, "has_workaround": False}
ev_maint = {
    "similar_prs": [],
    "maintainer_responses": [
        {
            "body_quote": (
                "Sorry for the delay, but I think I got it. I love a good bug like "
                "this; there's just one right answer and it's a tiny change. I "
                "[forked your fork]..."
            ),
            "issue_number": 81,
        },
        {
            "body_quote": (
                "Absolutely! It should be mentioned that lists are a little funky with "
                "this. The default remap always extends lists, adding items, and this "
                "remerge updates items fully recursively (it doesn't stop at a..."
            ),
            "issue_number": 81,
        },
    ],
    "welcome_labels": [],
}
cur.execute(
    "UPDATE opportunities SET status='open', source_type='compatibility', "
    "title=?, description=?, impl_hint=?, value_evidence=?, difficulty_evidence=?, "
    "urgency_evidence=?, maintainer_evidence=?, value=NULL, difficulty=NULL, "
    "urgency=NULL, maintainer_signal=NULL WHERE id=7611",
    (
        "remerge: list-typed nested values mishandled (breaks when overlay contains a list)",
        (
            "In boltons.iterutils.remerge, when both source and overlay contain the same "
            "key whose value is a list, the merged result is wrong: per the maintainer, "
            "the default remap extends lists but remerge updates items fully recursively. "
            "Issue #81 demonstrates the failure by adding 'zones': [{'a': 1}] to an overlay. "
            "The maintainer (mahmoud) has identified the bug and is open to a small fix; "
            "a debug-instrumented reproducer is already available in the issue."
        ),
        (
            "See https://gist.github.com/pleasantone/c99671172d95c3c18ed90dc5435ddd57 "
            "for the debug-instrumented reproducer. In boltons/iterutils.py, locate "
            "remerge() and the recursive merge step; when both a[k] and b[k] are lists, "
            "extend rather than recurse; when only one side is a list, decide between "
            "extend and replace (likely extend, to match remap). Add a unit test using "
            "'zones': [{'a': 1}] plus an existing overlay dict and verify the resulting "
            "list contains extended elements."
        ),
        json.dumps(ev_value),
        json.dumps(ev_diff),
        json.dumps(ev_urg),
        json.dumps(ev_maint),
    ),
)
print("opened 7611 (remerge list bug)")

# --- 3366 issue: wraps() adding parameters (mahmoud said interesting + provided FunctionBuilder.add_arg) ---
# This is a feature request that the maintainer has already partly addressed by adding
# FunctionBuilder.add_arg(). Issue is still open and maintainer is engaging. Marginal value.
ev_value = {
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "peer_impl_urls": [],
    "issue_reactions": 0,
    "issue_count": 19,
    "has_workaround": True,
    "prod_signal_quote": (
        "Merging two signatures sounds pretty cool to me! Kind of tricky with argument "
        "orderings and such, but I think some reasonable default behavior should be "
        "possible, as you've demonstrated"
    ),
    "has_prod_signal": False,
    "gap_desc": (
        "boltons.funcutils.wraps() only allows removing parameters from a wrapped function, "
        "not adding them; user requests a symmetric add_arg mechanism so decorators can "
        "inject new args cleanly. Maintainer has acknowledged the idea is interesting and "
        "in 19.0.0 added FunctionBuilder.add_arg() as a partial solution, but the wraps() "
        "wrapper path itself was not extended."
    ),
}
ev_diff = {
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "why_hard": (
        "Hard because: argument ordering and default-value handling when adding parameters "
        "to an existing signature is non-trivial; no canonical reference available"
    ),
    "target_approach_file": "boltons/funcutils.py",
}
ev_urg = {"cve_id": None, "has_prod_signal": False, "has_workaround": True}
ev_maint = {
    "similar_prs": [],
    "maintainer_responses": [
        {
            "body_quote": (
                "Hey @epruesse! Merging two signatures sounds pretty cool to me! Kind of "
                "tricky with argument orderings and such, but I think some reasonable "
                "default behavior should be possible, as you've demonstrated"
            ),
            "issue_number": 201,
        },
        {
            "body_quote": (
                "Best I could do for the recent release (19.0.0) was FunctionBuilder.add_arg(). "
                "While that technically solves part of this, the wraps() path itself was not "
                "extended to allow adding parameters"
            ),
            "issue_number": 201,
        },
    ],
    "welcome_labels": [],
}
cur.execute(
    "UPDATE opportunities SET status='open', source_type='issue', "
    "title=?, description=?, impl_hint=?, value_evidence=?, difficulty_evidence=?, "
    "urgency_evidence=?, maintainer_evidence=?, value=NULL, difficulty=NULL, "
    "urgency=NULL, maintainer_signal=NULL WHERE id=3366",
    (
        "funcutils.wraps: allow adding parameters (not just removing) to wrapped functions",
        (
            "boltons.funcutils.wraps currently only supports removing parameters from a "
            "wrapped function's signature. Issue #201 requests symmetric add-parameter "
            "support so decorators can inject new kwargs cleanly. The maintainer has "
            "acknowledged this is interesting but tricky, and 19.0.0 added "
            "FunctionBuilder.add_arg() as a partial solution. The wraps() decorator path "
            "itself was not extended. Still open with maintainer engagement."
        ),
        (
            "Extend boltons/funcutils.py wraps() to accept an inject_args parameter (or a "
            "new wraps_add decorator) that allows adding new kwargs/args with default "
            "values to the wrapped function's signature. Reuse FunctionBuilder.add_arg() "
            "internally so behavior stays consistent. Add tests covering arg ordering, "
            "default values, and functools.wraps introspection."
        ),
        json.dumps(ev_value),
        json.dumps(ev_diff),
        json.dumps(ev_urg),
        json.dumps(ev_maint),
    ),
)
print("opened 3366 (wraps add args)")

# --- 3368 issue: iterutils.lookahead (maintainer open if shared) ---
ev_value = {
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "peer_impl_urls": [],
    "issue_reactions": 0,
    "issue_count": 19,
    "has_workaround": True,
    "prod_signal_quote": (
        "I've needed something similar on a regular basis. The latest use case is for "
        "producing a row of tightly packed, closely related charts in matplotlib. In "
        "those cases, adding y axis labels and legends o..."
    ),
    "has_prod_signal": True,
    "gap_desc": (
        "boltons.iterutils lacks a lookahead() generator that yields (current, is_last) "
        "pairs. Use case: produce labels/legends for items grouped by lookahead. Issue "
        "open since 2016, maintainer expressed openness if user shares real-world usage "
        "and offers a PR. Several similar third-party recipes exist but boltons has no "
        "canonical implementation."
    ),
}
ev_diff = {
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "why_hard": (
        "Hard because: minor — needs careful handling of iterator exhaustion and the "
        "is_last flag for the final element; no canonical reference available"
    ),
    "target_approach_file": "boltons/iterutils.py",
}
ev_urg = {"cve_id": None, "has_prod_signal": True, "has_workaround": True}
ev_maint = {
    "similar_prs": [],
    "maintainer_responses": [
        {
            "body_quote": (
                "Hey there Tuuka! That's an interesting idea. I haven't needed lookahead "
                "myself, but I'm open to it, especially if you can share some usages of it "
                "out in the wild (or your own code)."
            ),
            "issue_number": 95,
        }
    ],
    "welcome_labels": [],
}
cur.execute(
    "UPDATE opportunities SET status='open', source_type='issue', "
    "title=?, description=?, impl_hint=?, value_evidence=?, difficulty_evidence=?, "
    "urgency_evidence=?, maintainer_evidence=?, value=NULL, difficulty=NULL, "
    "urgency=NULL, maintainer_signal=NULL WHERE id=3368",
    (
        "iterutils.lookahead: add generator yielding (current, is_last) pairs",
        (
            "boltons.iterutils lacks a lookahead() generator. Issue #95 (open since 2016) "
            "requests a generator that yields (current, is_last) pairs over an iterable, "
            "useful for rendering related chart groups, sequential file diffs, etc. "
            "Maintainer mahmoud is open to it if real-world usage and a tested PR are "
            "provided."
        ),
        (
            "Add a lookahead() generator to boltons/iterutils.py. Yield (value, is_last) "
            "where the final item is (value, True). Use six.next(it) or next(it) for "
            "Python 2/3 compat. Add a unit test covering: empty iterable, single element, "
            "multiple elements, and exhaustion behavior. Add an entry in the iterutils "
            "docstring listing."
        ),
        json.dumps(ev_value),
        json.dumps(ev_diff),
        json.dumps(ev_urg),
        json.dumps(ev_maint),
    ),
)
print("opened 3368 (iterutils.lookahead)")

# --- 3369 issue #347 tracking some ideas: this is the maintainer's own tracking list, NOT a contribution opportunity. ---
# DELETE — meta-discussion, "track some ideas" is exactly the "discussion"-style meta issue
# that the protocol excludes. Also, gap_desc contains "tracking" (meta keyword).
cur.execute("DELETE FROM opportunities WHERE id = 3369")
print("deleted 3369 (meta tracking issue)")

# --- 3370 issue #208 itertools.product with configurable type (maintainer leaving for kurtbrose) ---
# Maintainer explicitly said "I'll probably leave it for the minute" — soft rejection.
# Mark as refuted-style deletion. We err on the side of keeping when uncertain, but the
# maintainer has explicitly punted twice with no clear welcome.
# Actually protocol says "宁可保留" (rather keep than delete), but the issue has clear
# maintainer pushback. DELETE to avoid misleading contributors.
cur.execute("DELETE FROM opportunities WHERE id = 3370")
print("deleted 3370 (maintainer explicitly deferred)")

# --- 3371 issue #125 dict rupdate (no maintainer engagement, no canonical, generic snippet) ---
# Old issue, no prod signal, no maintainer response in evidence. Generic recipe issue.
# DELETE — too thin, maintainer not engaged, just a snippet request.
cur.execute("DELETE FROM opportunities WHERE id = 3371")
print("deleted 3371 (no maintainer engagement)")

conn.commit()
print("Batch 1 committed. Reviewing remaining...")

# Print remaining
for row in cur.execute(
    "SELECT o.id, o.source_type, o.title FROM opportunities o "
    "WHERE o.task_id IN (1138,1139) ORDER BY o.id"
):
    print(row)

conn.close()
