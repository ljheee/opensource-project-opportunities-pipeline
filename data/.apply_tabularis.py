#!/usr/bin/env python3
"""Stage 4 v2 batch judgment: TabularisDB/tabularis (task 1188)."""
import sqlite3, json

DB = 'data/pipeline.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()

def delete_opp(opp_id, why):
    cur.execute("DELETE FROM opportunities WHERE id = ?", (opp_id,))
    print(f"DELETE {opp_id}: {why}")

def promote(opp_id, **kw):
    cur.execute("""
        UPDATE opportunities SET
            status='open',
            source_type=?, title=?, description=?, impl_hint=?,
            value_evidence=?, difficulty_evidence=?, urgency_evidence=?, maintainer_evidence=?,
            value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
        WHERE id=?
    """, (kw['source_type'], kw['title'], kw['description'], kw['impl_hint'],
          json.dumps(kw['value_evidence']), json.dumps(kw['difficulty_evidence']),
          json.dumps(kw['urgency_evidence']), json.dumps(kw['maintainer_evidence']),
          opp_id))
    print(f"PROMOTE {opp_id} -> open ({kw['source_type']}): {kw['title']}")

# .ide = .idea (JetBrains IDE config dotfile -> blacklisted)
# features = Eclipse RCP feature manifests (build-system artifact)
# product = Eclipse RCP product definition (build-system artifact)
delete_opp(7770, "dbeaver '.ide' is JetBrains .idea dotfile (blacklisted)")
delete_opp(7771, "dbeaver 'features' is Eclipse RCP feature manifests (build artifact, not user-facing feature)")
delete_opp(7772, "dbeaver 'product' is Eclipse RCP product definition (build artifact, not user-facing feature)")

# 7774 — compat bug, kubectl port-forward
promote(7774,
    source_type='compatibility',
    title='[Bug] Cannot connect to PostgreSQL via kubectl port-forward while pgAdmin works',
    description="Tabularis fails to resolve the hostname exposed by `kubectl port-forward` (`failed to lookup address information: nodename nor servname provided, or not known`) whereas pgAdmin and psql on the same machine succeed. Indicates Tabularis's hostname/DNS resolution path is broken for localhost forwarding scenarios.",
    impl_hint="Inspect the connection-parameter parser and compare with how a working client (psql/pgAdmin) handles `localhost`/port-forwarded hostnames. Likely culprit: Node `dns.lookup` family override (IPv4 vs IPv6) or a synchronous DNS call that should be async.",
    value_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 28,
        "has_workaround": False,
        "prod_signal_quote": "Tabularis fails to connect to a PostgreSQL instance exposed locally via kubectl port-forward ... failed to lookup address information ... However, the same database connection works correctly when using pgAdmin and psql.",
        "has_prod_signal": True,
        "gap_desc": "Tabularis's hostname resolution differs from peers (pgAdmin, psql) for `kubectl port-forward`-exposed local PostgreSQL instances, breaking dev/k8s workflows"
    },
    difficulty_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: involves Node DNS resolution semantics that differ across platforms; needs cross-check against psql/pgAdmin behavior",
        "target_approach_file": "src/services/connection"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    maintainer_evidence={
        "similar_prs": [],
        "maintainer_responses": [
            {"body_quote": "Thanks for feedback. Are you able to debug from code? I am afk now but I can do a check later"},
            {"body_quote": "@getsueineko i suspected is something related to localhost resolution. But i am afk."}
        ],
        "welcome_labels": []
    })

# 7775 — compat bug, editor resets on tab switch
promote(7775,
    source_type='compatibility',
    title='[Bug] Editor query resets when switching between console tabs',
    description="Editing a SQL query in one console and then opening another console discards the in-memory edit; switching back shows the default `select * from ...` instead of the user's typed text. Confirmed in Tabularis 0.9.9 on Windows 10.",
    impl_hint="Investigate the tab state-management path for the console pane. The bug implies per-tab editor state isn't keyed by tab id. Add a unit test that asserts state persistence across tab switches.",
    value_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 23,
        "has_workaround": False,
        "prod_signal_quote": "If I edit a query in 'console 1', then open 'console 2', I lose my query when I go back to 'console 1'. I have the default 'select * from ...' instead.",
        "has_prod_signal": True,
        "gap_desc": "Console tab state is shared across tabs instead of being keyed by tab id; user edits are silently overwritten when switching consoles"
    },
    difficulty_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: needs to audit and refactor console tab state container; risk of regressions in unrelated panes",
        "target_approach_file": "src/components/console"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    maintainer_evidence={
        "similar_prs": [],
        "maintainer_responses": [
            {"body_quote": "@Mazwak Yes, I know. The challenge in this case is: keep data saved in memory on switching tabs."},
            {"body_quote": "Ah ok, this is a bug for sure. Do you want do do a check in the code?"}
        ],
        "welcome_labels": []
    })

# 5878 — read-only connection limiter (security)
promote(5878,
    source_type='security',
    title='[Feat] Read-only connection limiter support (mitigates destructive text2sql)',
    description="Tabularis's text2sql feature may generate UPDATE/DELETE/INSERT statements that mutate the database. A connection-level read-only mode (mirroring pgAdmin's 'Read Only' toggle) would prevent unintended destructive operations. Maintainer confirms the warning UX exists already in PR #473 and is open to a stricter limiter.",
    impl_hint="Extend the existing production-guard context (introduced in PR #473) with a per-connection `readOnly: boolean` flag. For postgres, issue `SET TRANSACTION READ ONLY`; for other drivers, gate statement execution at the parser layer. Add a UI toggle in the connection panel.",
    value_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 1,
        "issue_count": 31,
        "has_workaround": False,
        "prod_signal_quote": "Since this has support for text2sql (which is fantastic btw!) - one of the issues that users can run into is an unintended sql getting generated which can make changes to the database ... Having a read only connection mode would alleviate thi[s].",
        "has_prod_signal": True,
        "gap_desc": "No per-connection read-only enforcement; text2sql can produce destructive DML/DDL that mutates production data"
    },
    difficulty_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: needs per-driver wrappers for postgres/mysql/etc. and a UI toggle wired into the existing production-guard context",
        "target_approach_file": "src/contexts/ProductionGuardContext.tsx"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    maintainer_evidence={
        "similar_prs": [],
        "maintainer_responses": [
            {"body_quote": "It would certainly be possible to work on a mechanism that warns users before executing potentially destructive queries. This behavior is already implem[ented] ..."},
            {"body_quote": "Yeah, we can add it @zaits07 @sausin Would you be insterested in open a PR for it?"}
        ],
        "welcome_labels": []
    })

# 5882 — issue, render columns by size not type
promote(5882,
    source_type='issue',
    title='[Feat] Render columns based on column size instead of only types',
    description="Table view in Tabularis renders columns purely based on column type, producing awkward cell widths for data that should naturally be narrower (e.g. UUID as VARBINARY(36), short enums, fixed-length codes). User asks for size-aware column rendering.",
    impl_hint="Extend the column-width heuristic in the result-table component to also consider the actual data size of cells, not just the declared SQL type. Use sampling (first N rows) to estimate display width without forcing a full scan.",
    value_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 31,
        "has_workaround": False,
        "prod_signal_quote": "We store UUIDv4 AS VARBINARY(36) and this update broke the table view for me. ... This is the same table from [TablePlus] ...",
        "has_prod_signal": True,
        "gap_desc": "Result table in Tabularis sizes columns solely by declared SQL type; data-size-aware sizing is missing (TablePlus and others do this)"
    },
    difficulty_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: requires sampling-based width estimation without breaking virtualization or virtualized-row rendering",
        "target_approach_file": "src/components/results"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    maintainer_evidence={
        "similar_prs": [
            {"number": 499, "title": "feat(indexes): render functional/expression indexes across drivers", "merged": True, "url": "https://github.com/TabularisDB/tabularis/pull/499", "age_days": 40, "maintainer_comment": ""},
            {"number": 450, "title": "feat(postgres): support pgvector columns (vector, halfvec, sparsevec)", "merged": True, "url": "https://github.com/TabularisDB/tabularis/pull/450", "age_days": 52, "maintainer_comment": ""},
            {"number": 354, "title": "Feat/customizable result colors", "merged": True, "url": "https://github.com/TabularisDB/tabularis/pull/354", "age_days": 68, "maintainer_comment": ""}
        ],
        "maintainer_responses": [
            {"body_quote": "It should be fixed with this commit: ... Wll be online in next release"},
            {"body_quote": "Tested now, but it looks ok. Are you sure you are in the latest ver[sion]"}
        ],
        "welcome_labels": []
    })

# 7777 — issue, compact table view
promote(7777,
    source_type='issue',
    title='[Feat] Compact table view option to reduce vertical cell padding',
    description="Current Tabularis table view uses excessive internal cell padding, wasting vertical space. User asks for a compact mode that reduces padding to show more rows per viewport. Maintainer invites a PR.",
    impl_hint="Add a CSS modifier class on the result-table component that reduces `padding` on `td`/`th`, and expose a UI toggle (Settings or view-mode menu) to switch between default and compact density.",
    value_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 30,
        "has_workaround": False,
        "prod_signal_quote": "The current table view in TabularisDB uses excessive internal cell padding, causing rows to consume unnecessary vertical space. We need a compact table view option that reduces these margins to display more data rows within the same viewport.",
        "has_prod_signal": True,
        "gap_desc": "Tabularis offers no compact-density mode for the result table; users on small screens must scroll heavily"
    },
    difficulty_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: trivial CSS work, but must hook into user-settings persistence so the toggle survives restarts",
        "target_approach_file": "src/components/results"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    maintainer_evidence={
        "similar_prs": [],
        "maintainer_responses": [
            {"body_quote": "Hi @user5434, thanks for your feedback! Looks very easy to do, do you want create a PR for this?"}
        ],
        "welcome_labels": []
    })

# 7778 — issue, transparent background on Windows icon
# This is purely a visual asset/icon tweak with no functional impact.
# Low value, but maintainer explicitly invites contribution. Promote.
promote(7778,
    source_type='issue',
    title='[Feat] Transparent background on Windows app icon',
    description="The Windows app icon for Tabularis renders with a non-transparent background, making it visually inconsistent with the GitHub icon and the app's own favicon. Maintainer agrees and invites a contribution.",
    impl_hint="Replace the existing Windows .ico asset with one whose background layer is removed (PNG-with-alpha -> .ico). Use `magick convert` or rebuild from the source SVG. Update any installer resource bundling.",
    value_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 27,
        "has_workaround": False,
        "prod_signal_quote": "So the icons are percieved different between: App, Github and Icon for the app.",
        "has_prod_signal": True,
        "gap_desc": "Windows app icon lacks a transparent background, making it visually inconsistent with the GitHub icon and other assets"
    },
    difficulty_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: trivial asset swap, but requires regenerating the .ico with proper alpha and ensuring electron-builder picks it up",
        "target_approach_file": "build/icon"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    maintainer_evidence={
        "similar_prs": [],
        "maintainer_responses": [
            {"body_quote": "@MischaKr Yeah, totally agree. ... What do you think is the best? No background - White background - Grey background - Other option."},
            {"body_quote": "@MischaKr of course feel free to propose or contribute directly :)"}
        ],
        "welcome_labels": []
    })

conn.commit()
conn.close()
print("TabularisDB/tabularis batch complete")