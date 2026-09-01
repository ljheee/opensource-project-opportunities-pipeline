#!/usr/bin/env python3
"""Apply Stage 4 v2 batch judgment for tasks 1440, 1441, 1442 (date 2026-08-31)."""
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


# ============================================================
# Task 1440: bfenetworks/bfe (no canonical reference)
# ============================================================
print("=== Task 1440: bfenetworks/bfe ===")

# 8435: WASM panic — real bug
update_open(
    8435, "issue",
    "Unrecovered panic in WASM plugin loading crashes entire BFE process",
    "A malformed .wasm plugin file causes an unrecovered panic that kills the entire BFE process, both at startup (mod_wasm load) and during config reload (/reload/mod_wasm). plugin.go:251 uses panic(err) on RegisterImports failure while every other error in the same function uses log.Errorf; a single bad plugin causes a full outage with all traffic dropped. Fix: wrap the wasm call site in a func() that calls recover() and translates recovered values to error returns so BFE keeps serving unaffected plugins.",
    "Wrap the failing plugin loader path (bfe_wasmplugin/plugin.go near the RegisterImports call) so that runtime panics from the wasm runtime are caught via defer recover() and surfaced as a non-fatal error log; skip the bad plugin rather than killing the process. Add an integration test that loads a directory containing both valid and malformed .wasm files and asserts BFE stays alive.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 0,
        "has_workaround": False,
        "prod_signal_quote": "PRODUCTION DEMO: BFE with WASM panic recovery 1. BFE running with valid WASM plugin: ALIVE 3. Loading MALFORMED .wasm via hot re",
        "has_prod_signal": True,
        "gap_desc": "Single malformed .wasm plugin file takes down the entire BFE process because the wasm loader uses panic(err) instead of returning an error."
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Requires adding defer recover() boundaries around all wasm runtime entry points and propagating errors to callers that today only handle panic recovery implicitly; needs careful testing under config-reload concurrency.",
        "target_approach_file": "bfe_wasmplugin/plugin.go"
    },
    {"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    {
        "similar_prs": [],
        "maintainer_responses": [],
        "welcome_labels": []
    },
)
print("  8435 -> open")

# 3380: HTTP/3
update_open(
    3380, "issue",
    "Add HTTP/3 (QUIC) protocol support",
    "BFE currently serves HTTP/1.1 and HTTP/2 but lacks HTTP/3 over QUIC. Adding HTTP/3 would let operators terminate QUIC at the edge (lower handshake latency, multiplexed streams without head-of-line blocking, better mobile experience) and unify protocol negotiation in one place instead of stacking a separate QUIC frontend.",
    "Stand up a QUIC listener alongside the existing TLS listener using a mature Go QUIC implementation (e.g. quic-go). Bridge ALPN matching so the same BFE config routes by :authority and :path. Add a config knob (e.g. enable_http3) and ensure the existing connection-balancing pipeline does not regress on 0-RTT handling.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 1,
        "issue_count": 1,
        "has_workaround": False,
        "prod_signal_quote": "",
        "has_prod_signal": False,
        "gap_desc": "BFE lacks HTTP/3 over QUIC support — edge load balancer cannot serve modern clients with QUIC's latency and head-of-line-blocking benefits."
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: HTTP/3 needs a QUIC implementation integrated with BFE's existing TLS/ALPN config and connection-balancing pipeline; concurrent streams and 0-RTT replay protection are non-trivial.",
        "target_approach_file": "bfe_server/"
    },
    {"cve_id": None, "has_prod_signal": False, "has_workaround": False},
    {
        "similar_prs": [],
        "maintainer_responses": [],
        "welcome_labels": ["enhancement"]
    },
)
print("  3380 -> open")

# 3383: Active health check
update_open(
    3383, "issue",
    "Add active health check support for backends",
    "BFE today only does passive health checks (outlier detection using responses from real requests). Operators want to actively and periodically probe each backend instance and remove unhealthy ones even when no real traffic is hitting them. Add an active probe scheduler (HTTP/HTTPS/TCP), a CheckMode config in BackendCheckConfig, and integrate the probe results with the existing load-balancer scoring.",
    "Add a new package bfe_balance/checker that periodically issues probes against each backend instance (configurable interval/timeout), stores last-success timestamp, and exposes a Health() method. Wire the result into the existing balancer so a failed probe marks the instance as unavailable until N consecutive successes recover it.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 3,
        "has_workaround": False,
        "prod_signal_quote": "",
        "has_prod_signal": False,
        "gap_desc": "BFE only supports passive health checks; operators cannot reliably evict dead backends during low-traffic windows or before first user request."
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: probes must run on a separate goroutine pool without contending with the request hot path; integration with the balancer's instance scoring requires careful synchronization.",
        "target_approach_file": "bfe_balance/bfe_balance_check.go"
    },
    {"cve_id": None, "has_prod_signal": False, "has_workaround": False},
    {
        "similar_prs": [],
        "maintainer_responses": [
            {"author_association": "MEMBER", "body_quote": "@nitishm Thanks for your contribution! The issue has been updated.", "issue_number": 385}
        ],
        "welcome_labels": ["good first issue"]
    },
)
print("  3383 -> open")

# 8434: BFE RFC violation
update_open(
    8434, "issue",
    "BFE forwards requests with empty HTTP method instead of rejecting per RFC 7230",
    "If an incoming request has an empty HTTP method string, BFE substitutes GET as a default during forwarding. RFC 7230 requires the request method to be at least one character; an invalid request line should produce 400 or redirect, like Apache/Nginx/Tomcat do. BFE silently rewrites and forwards malformed requests, masking broken clients and breaking conformance with mainstream web servers.",
    "In the request-line parser (bfe_http/request.go or equivalent), reject any request whose method field is empty by returning 400 Bad Request instead of defaulting to GET. Add a regression test that sends a raw request line with an empty method and asserts the 400 response.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 0,
        "has_workaround": False,
        "prod_signal_quote": "定了HTTP请求方法至少为1个字符，不能为空字符串；当遇到无效的请求行时，服务器应该明确拒绝，返回400或者重定向。 在主流的Web服务器中（如Apache、Nginx、Tomcat等）都会显式拒绝畸形的空字符串请求方法。",
        "has_prod_signal": True,
        "gap_desc": "BFE silently rewrites empty HTTP method to GET instead of rejecting per RFC 7230, diverging from Apache/Nginx/Tomcat behavior."
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: the parser sits on the request hot path and a wrong error mapping can break legitimate clients; needs careful test coverage on edge cases like whitespace-only methods.",
        "target_approach_file": "bfe_http/request.go"
    },
    {"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    {
        "similar_prs": [],
        "maintainer_responses": [],
        "welcome_labels": []
    },
)
print("  8434 -> open")

# 8428: mod_mime — DELETE (3381 already open with same source_ref)
delete_draft(8428)
print("  8428 -> DELETE (duplicate of open opp 3381)")

# 8429: JWT WebSocket — DELETE (3382 already open with same source_ref)
delete_draft(8429)
print("  8429 -> DELETE (duplicate of open opp 3382)")

# DELETEs for task 1440
delete_draft(3384)
print("  3384 -> DELETE (meta-discussion)")
delete_draft(3385)
print("  3385 -> DELETE (user dev-workflow question)")
delete_draft(8426)
print("  8426 -> DELETE (user showcase thread)")
delete_draft(8432)
print("  8432 -> DELETE (already fixed per maintainer commit)")

done_task(1440, "bfenetworks/bfe")
print("  Task 1440 -> done")

con.commit()
print("\nCommitted task 1440 changes.")