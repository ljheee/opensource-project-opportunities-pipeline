#!/usr/bin/env python3
"""Apply Stage 4 v2 batch judgment for task 1441 (cloudquery/cloudquery)."""
import json
import sqlite3
from datetime import datetime, timezone

DB = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"
NOW = datetime.now(timezone.utc).isoformat()

con = sqlite3.connect(DB)
cur = con.cursor()


def update_open(opp_id, source_type, title, description, impl_hint,
                value_ev, difficulty_ev, urgency_ev, maintainer_ev):
    cur.execute(
        """UPDATE opportunities
           SET status='open',
               source_type=?, title=?, description=?, impl_hint=?,
               value_evidence=?, difficulty_evidence=?, urgency_evidence=?,
               maintainer_evidence=?,
               value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
           WHERE id=?""",
        (source_type, title, description, impl_hint,
         json.dumps(value_ev), json.dumps(difficulty_ev),
         json.dumps(urgency_ev), json.dumps(maintainer_ev), opp_id)
    )


def delete_draft(opp_id):
    cur.execute("DELETE FROM opportunities WHERE id=? AND status='draft'", (opp_id,))


def done_task(task_id, project_id):
    cur.execute("UPDATE tasks SET status='done', finished_at=? WHERE id=?",
                (NOW, task_id))
    cur.execute("UPDATE projects SET status='active' WHERE id=? AND status='analyzing'",
                (project_id,))


print("=== Task 1441: cloudquery/cloudquery ===")

# DELETEs (duplicates with already-open opps)
delete_draft(8416)
print("  8416 -> DELETE (duplicate of open opp 4977)")
delete_draft(8421)
print("  8421 -> DELETE (duplicate of open opp 4982)")
delete_draft(8422)
print("  8422 -> DELETE (duplicate of open opp 4984)")
delete_draft(8424)
print("  8424 -> DELETE (duplicate of open opp 4986)")
delete_draft(4978)
print("  4978 -> DELETE (duplicate of open opp 625)")
delete_draft(4981)
print("  4981 -> DELETE (duplicate of open opp 626)")

# 8425: Azure cloud_name docs bug — still open (state_reason=reopened)
update_open(
    8425, "issue",
    "Azure plugin documentation lists invalid cloud_name values",
    "CloudQuery Azure docs list cloud_name options AzureCloud / AzureChinaCloud / AzureGovernment, but the SDK only accepts AzurePublic / AzureGovernment / AzureChina. Following the docs gives `unknown Azure cloud name 'AzureCloud'` at plugin init. Document the real accepted values (AzurePublic / AzureGovernment / AzureChina) and align the SDK error message so the names match the docs.",
    "Update the Azure plugin docs (plugins/source/azure/docs/) to list AzurePublic / AzureGovernment / AzureChina as the only supported cloud_name values. Optionally tighten the SDK validator's accepted enum and add a regression test that asserts every documented cloud_name is accepted by the SDK.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 1,
        "issue_count": 1,
        "has_workaround": False,
        "prod_signal_quote": "error: code = Internal desc = failed to init plugin: failed to initialize client: unknown Azure cloud name 'AzureCloud'. Supported values are ['AzurePublic', 'AzureGovernment', 'AzureChina'].",
        "has_prod_signal": True,
        "gap_desc": "CloudQuery Azure plugin documentation lists cloud_name values (AzureCloud) that the SDK rejects at startup, breaking first-run setup for users following the official docs."
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Easy: a documentation fix plus aligning the SDK error message. Mostly textual, low implementation effort.",
        "target_approach_file": "plugins/source/azure/docs/"
    },
    {"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    {
        "similar_prs": [],
        "maintainer_responses": [{"body_quote": "Good catch @ukbe should be fixed now", "issue_number": 20445}],
        "welcome_labels": ["kind/docs", "kind/bug"]
    },
)
print("  8425 -> open")

# 4979: CDC for tables added after sync starts
update_open(
    4979, "issue",
    "CDC: sync tables that get created after the sync starts",
    "CloudQuery CDC currently takes a fixed table list at sync start; tables added during the sync are never picked up until the next full sync. Requested by a user on Discord: add a flag to enable post-startup discovery so newly added tables begin syncing without restarting the CLI.",
    "Extend the CDC source plugin interface (plugins/source/) so each plugin can register a periodic table-list refresh and emit new tables into the existing CDC stream. Add a config knob (e.g. cdc.refresh_interval / cdc.discover_new_tables) on the source side and reuse the destination's idempotent insert path for newly seen tables.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 3,
        "issue_count": 3,
        "has_workaround": True,
        "prod_signal_quote": "A possible (not so nice) workaround at the moment is to periodically kill the CLI and re-run it to sync the new tables",
        "has_prod_signal": True,
        "gap_desc": "CloudQuery CDC captures only the initial table list; tables added mid-sync are ignored until the next full restart, blocking zero-downtime schema evolution."
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: each source plugin must implement incremental table discovery without restarting; the CDC cursor must be extended to track new tables without re-syncing already-known ones.",
        "target_approach_file": "plugins/source/postgresql/"
    },
    {"cve_id": None, "has_prod_signal": True, "has_workaround": True},
    {
        "similar_prs": [],
        "maintainer_responses": [{"body_quote": "A possible (not so nice) workaround at the moment is to periodically kill the CLI and re-run it to sync the new tables", "issue_number": 9102}],
        "welcome_labels": ["kind/feat"]
    },
)
print("  4979 -> open")

# 4980: Temp table for transaction-based syncs
update_open(
    4980, "issue",
    "Destination-side temp table for transactional syncs",
    "In overwrite mode the destination database can be left in an inconsistent half-old / half-new state mid-sync because new data is written directly to the production tables. Implement a temp-table pattern: sync into a temporary table and atomically swap it into place at the end so consumers always see a consistent snapshot. Implementable destination-side without SDK changes.",
    "In the destination plugin (plugins/destination/postgresql or any DB destination), add a write mode flag (e.g. atomic_swap=true) that, when set, writes to a per-sync temp table and uses a single rename/transaction to swap it into the live table at end of sync. Add an integration test that simulates a sync crash mid-write and asserts the live table still holds the previous consistent state.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 3,
        "issue_count": 2,
        "has_workaround": False,
        "prod_signal_quote": "",
        "has_prod_signal": False,
        "gap_desc": "CloudQuery destination overwrite writes directly to live tables, leaving consumers with half-old / half-new data mid-sync."
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: temp-table swap semantics vary by destination (Postgres uses ALTER TABLE ... RENAME, BigQuery needs table copy + DML, ClickHouse needs non-Atomic engine handling). Each destination plugin needs a custom implementation behind a shared interface.",
        "target_approach_file": "plugins/destination/postgresql/"
    },
    {"cve_id": None, "has_prod_signal": False, "has_workaround": False},
    {
        "similar_prs": [],
        "maintainer_responses": [],
        "welcome_labels": ["kind/feat"]
    },
)
print("  4980 -> open")

# 4985: Relative timestamp support for AWS table_options
update_open(
    4985, "issue",
    "Relative timestamp support for AWS plugin table_options",
    "AWS plugin table_options currently only accepts absolute timestamps, forcing users to rely on env-var substitution or manual config edits to roll the time window. Add a unified way to express relative timestamps (e.g. '-7d', '-1h') at runtime so config files can stay static across deployments. Java reference implementation already uses `-` to indicate a relative offset; port that pattern to the Go AWS plugin config schema.",
    "Extend the AWS plugin's table_options timestamp parsing (plugins/source/aws/spec.go or similar) to accept ISO-8601 relative durations prefixed with `-`. Resolve the relative timestamp to an absolute RFC3339 value at sync start. Mirror the Java SDK syntax and document the supported grammar in plugins/source/aws/docs/.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 1,
        "issue_count": 2,
        "has_workaround": False,
        "prod_signal_quote": "",
        "has_prod_signal": False,
        "gap_desc": "AWS plugin table_options only accepts absolute timestamps; users must swap env vars or edit configs to roll the time window, breaking static-config workflows."
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Medium. The duration parser itself is easy (time.ParseDuration + ISO-8601 extension), but propagating the resolved timestamp through the existing AWS API filters without breaking absolute-time callers needs careful refactor.",
        "target_approach_file": "plugins/source/aws/spec.go"
    },
    {"cve_id": None, "has_prod_signal": False, "has_workaround": False},
    {
        "similar_prs": [],
        "maintainer_responses": [{"body_quote": "Would need a few things to clarify in the syntax: Relative in what direction? (going from now to past? probably... so we might omit creating future timestamps I guess) Functionality to truncat", "issue_number": 11663}],
        "welcome_labels": ["kind/feat"]
    },
)
print("  4985 -> open")

done_task(1441, "cloudquery/cloudquery")
print("  Task 1441 -> done")

con.commit()
print("\nCommitted task 1441 changes.")