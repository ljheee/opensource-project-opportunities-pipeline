#!/usr/bin/env python3
"""Apply patroni (task 1522) draft judgments."""
import json
import sqlite3
from pathlib import Path

DB = Path("/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db")

con = sqlite3.connect(DB)
cur = con.cursor()

def upd(opp_id, source_type, title, description, impl_hint,
        value_evidence, difficulty_evidence, urgency_evidence, maintainer_evidence):
    cur.execute(
        """UPDATE opportunities
           SET status='open', source_type=?, title=?, description=?, impl_hint=?,
               value_evidence=?, difficulty_evidence=?, urgency_evidence=?, maintainer_evidence=?,
               value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
           WHERE id=?""",
        (source_type, title, description, impl_hint,
         json.dumps(value_evidence), json.dumps(difficulty_evidence),
         json.dumps(urgency_evidence), json.dumps(maintainer_evidence), opp_id),
    )

# DELETE duplicates of existing open opportunities on the same issue_number
for dup_id, issue_no in [
    (5344, 1759),  # open row 398
    (8632, 3431),  # open row 5340
    (8631, 3480),  # open row 5339
    (8634, 3194),  # open row 5342
    (8635, 3237),  # open row 397 and 5343
    (8639, 1637),  # maintainer says "no value in such a feature" -> rejected
]:
    cur.execute("DELETE FROM opportunities WHERE id=?", (dup_id,))

# 8637 — standby cluster in pause mode does not recover from wiped DCS (issue 3274)
upd(
    8637,
    "compatibility",
    "Make standby cluster restore /config from DCS when leaving pause mode",
    "A standby cluster that is put into pause mode and whose DCS is wiped does not recover: the primary cluster re-writes /leader, /initialize and /config, the standby does not. The fix is to re-write /config on the standby side after leaving pause mode (or any mode that disables writes), not only on the leader-lock holder.",
    "In the standby-cluster HA loop, after detecting that DCS was wiped (e.g. ConfigWriteRetry / missing /config), trigger a re-init of /config from local state when leaving pause mode, mirroring the leader-side path. Keep the existing primary-side behaviour. Reference: `patroni/ha.py` (`Ha`/`Patroni`/`StandbyCluster` classes).",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 23,
        "has_workaround": False,
        "prod_signal_quote": "If a primary cluster is in maintenance mode and the DCS is wiped (e.g. because one decides to migrate from etcd to etcd3), it re-writes the /leader, /initialize and /config keys to DCS on the next HA loop",
        "has_prod_signal": True,
        "gap_desc": "Standby cluster leaves pause mode with empty /config after a DCS wipe - asymmetric behaviour vs primary cluster",
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: involves HA loop concurrency and ConfigWriteRetry paths; needs careful staging to avoid double-write races.",
        "target_approach_file": "patroni/ha.py",
    },
    {"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    {"similar_prs": [
        {"number": 2648, "title": "Add docstrings and type hints to patroni/api.py", "merged": True, "url": "https://github.com/patroni/patroni/pull/2648", "age_days": 1229, "maintainer_comment": ""}
    ], "maintainer_responses": [
        {"body_quote": "I think it should restore keys after disabling maintenance mode. IMO better to do it with maintenance anyway, because we don't want to stop Postgres when we restart Patroni.", "issue_number": 3274}
    ], "welcome_labels": []},
)

# 5338 — Citus multi-database (issue 2567). Maintainer invited external contribution; reclassify as issue/feature.
upd(
    5338,
    "issue",
    "Support multiple Citus-enabled databases in the Patroni Citus integration",
    "The new Patroni Citus integration (docs/citus.html) only handles clusters with a single Citus-enabled database. Production users run a small number (5-10) of Citus-enabled databases per cluster and want to opt each one in independently.",
    "In `patroni/postgresql/citus.py` (and the corresponding config validation), change the citus section from single-database to a list/dict mapping per database. Add a `citus.databases` (or similar) config knob and update `citus_worker` queries to iterate. Migration: existing single-database configs should keep working via a deprecation shim. Add tests covering 2+ databases.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 13,
        "issue_count": 19,
        "has_workaround": False,
        "prod_signal_quote": "We're actively using Citus + Patroni with multiple citus-enabled databases in production and would really like to be able to use the new Citus integration with Patroni in our setup. Currently this integration only supports clusters with a single citus-enabled database which prevents us from using the new functionality.",
        "has_prod_signal": True,
        "gap_desc": "Patroni Citus integration only handles a single citus-enabled database; multi-tenant prod setups cannot adopt it",
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: requires redesigning the citus config schema (single -> list) and the worker scheduling queries; needs a deprecation path.",
        "target_approach_file": "patroni/postgresql/citus.py",
    },
    {"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    {"similar_prs": [], "maintainer_responses": [
        {"body_quote": "Usually people create many databases in a single cluster because they are small or because the host where cluster runs has a lot of hardware resources.", "issue_number": 2567},
        {"body_quote": "I am sorry, but we don't have plans to work on it. Patroni is an open-source project, if you really need this feature feel free to contribute.", "issue_number": 2567},
    ], "welcome_labels": []},
)

# 5341 — Consul service registration parameters (issue 1256). Maintainer inviting PRs.
upd(
    5341,
    "issue",
    "Make Consul service-registration definition customizable (tags, meta, sidecar hints)",
    "Patroni currently sends a fixed service definition to Consul on registration. Users want to customize tags, meta and Connect sidecar hints (e.g. `to start Consul Connect sidecar proxy`).",
    "Extend `patroni/consul.py`'s service registration call to read an optional `consul.register` config block (tags, meta, check interval, sidecar proxy config) and pass it through to the Consul HTTP API. Keep the default unchanged for backwards compatibility.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 5,
        "issue_count": 12,
        "has_workaround": False,
        "prod_signal_quote": "Is it possible to customize service definition sent to consul on service registration? For example - to start Consul Connect sidecar proxy.",
        "has_prod_signal": False,
        "gap_desc": "Consul service registration sends a fixed definition; users cannot add tags, meta or sidecar hints",
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: needs a new config schema, defaults, and tests for Consul registration payload; low runtime risk.",
        "target_approach_file": "patroni/consul.py",
    },
    {"cve_id": None, "has_prod_signal": False, "has_workaround": False},
    {"similar_prs": [], "maintainer_responses": [
        {"body_quote": "If somebody implements it, we will happily review and merge.", "issue_number": 1256},
        {"body_quote": "@archana-1209  I have no clue, but so far nobody implemented anything.", "issue_number": 1256},
    ], "welcome_labels": []},
)

# 5346 — creating replica not completed (issue 747). User-reported; contains diagnostic info.
upd(
    5346,
    "issue",
    "Patroni reinit of a replica never completes when leader LAG stays high",
    "When `patronictl reinit` is run on a replica while the leader LAG is ~1 GB, the reinit appears to run but never completes; free space drains then the loop restarts. The diagnostic path seems to keep choosing to retry instead of failing fast or making progress.",
    "Add tracing around the reinit bootstrap loop in `patroni/ha.py` (ReplicaBootstrap) to log each stage (basebackup, wal replay, promote) and add a configurable `reinit_timeout` that fails the reinit with a clear error after N minutes instead of looping. Optionally surface remaining lag in the same log line.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 19,
        "has_workaround": False,
        "prod_signal_quote": "One node with cluster patroni was off. After shut up Lag in MB was 1Gb and nothing happened for a long time.",
        "has_prod_signal": False,
        "gap_desc": "Replica reinit never fails or completes when leader LAG is large; users cannot tell whether the reinit is progressing",
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: reinit touches basebackup + WAL replay + promote; needs careful failure-mode semantics.",
        "target_approach_file": "patroni/ha.py",
    },
    {"cve_id": None, "has_prod_signal": False, "has_workaround": False},
    {"similar_prs": [], "maintainer_responses": [
        {"body_quote": "Hmm, I think we can do better job in verifying the state of the data directory. Most of the (good) backup tools will restore global/pg_control on the last step.", "issue_number": 747}
    ], "welcome_labels": []},
)

con.commit()
con.close()
print("patroni done")