#!/usr/bin/env python3
"""Apply judgment for task 1557 (grafana/tempo) - Stage 4 v2 batch."""
import sqlite3
import json
from datetime import datetime, timezone

DB = "data/pipeline.db"
NOW = "2026-09-01T18:30:00+00:00"

conn = sqlite3.connect(DB)
cur = conn.cursor()

# === UPDATE: 5158 issue:2493 (real enhancement, ruler) → OPEN ===
cur.execute("""
    UPDATE opportunities SET
        status='open',
        source_type='issue',
        title='Add a ruler to Tempo to create alerts with TraceQL queries.',
        description='User-reported enhancement: Tempo lacks a ruler-style component to evaluate TraceQL queries and emit metrics/alerts (similar to Loki''s LogQL ruler and Prometheus alerting rules). Without this, users cannot create alerts on span-level conditions (e.g. error-rate, latency percentiles) from within Tempo and must build an external pipeline.',
        impl_hint='Add a new modules/ruler/ package (mirroring Loki/Cortex ruler architecture) that evaluates TraceQL queries on a schedule and exposes a Prometheus remote_write endpoint; reuse query-frontend for query execution and the querier for backend access.',
        value_evidence=?,
        difficulty_evidence=?,
        urgency_evidence=?,
        maintainer_evidence=?,
        value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL,
        last_seen_at=?, updated_at=?
    WHERE id=5158
""", (
    json.dumps({
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 23,
        "issue_count": 14,
        "has_workaround": False,
        "prod_signal_quote": "tempo would most likely need a rate syntax (along with the sum, count, avg, etc to combine with that to produce numeric values) in order to align with loki on how they are doing logql to create alerts.",
        "has_prod_signal": True,
        "gap_desc": "Tempo lacks an in-built ruler/alerting component for TraceQL — users must run a separate Prometheus pipeline to alert on trace-derived metrics, duplicating effort that Loki (LogQL) and Prometheus (PromQL) already provide natively."
    }),
    json.dumps({
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: requires a new long-running evaluator (rule lifecycle, hot-reload from a config store, evaluation queueing); cross-cuts querier, query-frontend, and storage layers; needs query-rate/cost governance.",
        "target_approach_file": "modules/querier/ (consume) and a new modules/ruler/ package (evaluate)"
    }),
    json.dumps({"cve_id": None, "has_prod_signal": True, "has_workaround": False}),
    json.dumps({
        "similar_prs": [],
        "maintainer_responses": [
            {"author_association": "MEMBER", "body_quote": "this is something we want to tackle at some point, please stay tuned", "issue_number": 2493}
        ],
        "welcome_labels": ["enhancement", "keepalive"]
    }),
    NOW, NOW,
))
print(f"5158: {cur.rowcount} row updated")

# === DELETE: 8858 perf/issue:1508 — UNIQUE collision with verified row 5161 (issue/issue:1508) ===
cur.execute("DELETE FROM opportunities WHERE id=8858")
print(f"8858: {cur.rowcount} row deleted (UNIQUE collision with verified row 5161)")

# === UPDATE: 8860 issue:6566 (real regression bug) → OPEN ===
cur.execute("""
    UPDATE opportunities SET
        status='open',
        source_type='issue',
        title='regression: query_frontend.metrics.max_duration is inaccurate after upgrading to 2.10.1',
        description='Real bug regression: after upgrading to Tempo 2.10.1, the `query_frontend.metrics.max_duration` config is no longer honored correctly. Users overriding the default 3h window via Helm to 8h observe that the metric still reports 3h, leading to dropped metrics queries exceeding the (incorrectly reported) bound.',
        impl_hint='Audit query-frontend metrics-generator config wiring (modules/frontend/) for the v2.10.1 refactor; ensure user-supplied query_frontend.metrics.max_duration propagates into the metrics generator instead of being shadowed by the default.',
        value_evidence=?,
        difficulty_evidence=?,
        urgency_evidence=?,
        maintainer_evidence=?,
        value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL,
        last_seen_at=?, updated_at=?
    WHERE id=8860
""", (
    json.dumps({
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 4,
        "issue_count": 6,
        "has_workaround": False,
        "prod_signal_quote": "Start Tempo (2.10.1) with query_frontend.metrics.max_duration set to 8h. The metric still uses 3h default.",
        "has_prod_signal": True,
        "gap_desc": "Configuration override of query_frontend.metrics.max_duration is silently ignored after the 2.10.x release — the metric keeps reporting the hardcoded default 3h."
    }),
    json.dumps({
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: regression introduced by refactor; root cause likely a config merge order or default-precedence bug; needs tracing of overrides across modules/frontend + modules/generator wiring.",
        "target_approach_file": "modules/frontend/"
    }),
    json.dumps({"cve_id": None, "has_prod_signal": True, "has_workaround": False}),
    json.dumps({
        "similar_prs": [],
        "maintainer_responses": [],
        "welcome_labels": ["stale"]
    }),
    NOW, NOW,
))
print(f"8860: {cur.rowcount} row updated")

# === Mark task 1557 done & project active ===
cur.execute("UPDATE tasks SET status='done', finished_at=? WHERE id=1557", (NOW,))
print(f"task 1557: {cur.rowcount} row updated")
cur.execute("UPDATE projects SET status='active' WHERE id='grafana/tempo' AND status='analyzing'")
print(f"project grafana/tempo: {cur.rowcount} row updated")

conn.commit()
conn.close()
print("\n=== Task 1557 applied ===")