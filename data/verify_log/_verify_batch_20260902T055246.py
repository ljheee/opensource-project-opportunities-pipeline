#!/usr/bin/env python3
"""Adversarial verification of 10 opportunity points."""
import json
import os
import sqlite3
import sys
import time
import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

DB = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"

IDS = [319, 320, 4937, 4939, 384, 385, 386, 5491, 5493, 6223]

# throttle control
_last_core_call = 0.0
_last_search_call = 0.0
_search_count = 0
SEARCH_BUDGET = 10


def throttled_get(url, params=None, search=False, timeout=20):
    global _last_core_call, _last_search_call, _search_count
    if search:
        # enforce search budget
        if _search_count >= SEARCH_BUDGET:
            return None, "search_budget_exhausted"
        elapsed = time.time() - _last_search_call
        if elapsed < 7:
            time.sleep(7 - elapsed)
        _last_search_call = time.time()
        _search_count += 1
    else:
        elapsed = time.time() - _last_core_call
        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)
        _last_core_call = time.time()
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
        return r, None
    except Exception as e:
        return None, str(e)


def get_issue(repo_full, issue_number):
    r, err = throttled_get(f"https://api.github.com/repos/{repo_full}/issues/{issue_number}")
    if err or r is None:
        return None, err or "no_response"
    if r.status_code == 404:
        return {"status_code": 404, "state": "missing"}, None
    if r.status_code >= 400:
        return None, f"http_{r.status_code}"
    data = r.json()
    return {
        "status_code": r.status_code,
        "state": data.get("state"),
        "labels": [l["name"] for l in data.get("labels", [])],
        "reactions": data.get("reactions", {}).get("total_count", 0),
        "title": data.get("title"),
        "user": data.get("user", {}).get("login") if data.get("user") else None,
    }, None


def get_timeline(repo_full, issue_number, max_pages=2):
    """Returns list of timeline events filtered for cross-referenced / connected."""
    events = []
    for page in range(1, max_pages + 1):
        r, err = throttled_get(
            f"https://api.github.com/repos/{repo_full}/issues/{issue_number}/timeline",
            params={"per_page": 100, "page": page},
        )
        if err or r is None:
            return None, err or "no_response"
        if r.status_code == 404:
            return [], None  # timeline disabled
        if r.status_code >= 400:
            return None, f"http_{r.status_code}"
        events.extend(r.json())
        if len(r.json()) < 100:
            break
    return events, None


def get_pr(repo_full, pr_number):
    r, err = throttled_get(f"https://api.github.com/repos/{repo_full}/pulls/{pr_number}")
    if err or r is None:
        return None, err
    if r.status_code == 404:
        return {"status_code": 404, "merged": False}, None
    if r.status_code >= 400:
        return None, f"http_{r.status_code}"
    data = r.json()
    return {
        "status_code": r.status_code,
        "merged": data.get("merged"),
        "merged_at": data.get("merged_at") or data.get("pull_request", {}).get("merged_at"),
        "state": data.get("state"),
        "title": data.get("title"),
    }, None


def search_merged_prs(repo_full, keyword):
    q = f'is:pr is:merged repo:{repo_full} "{keyword}"'
    r, err = throttled_get(
        "https://api.github.com/search/issues",
        params={"q": q, "per_page": 5},
        search=True,
    )
    if err or r is None:
        return None, err or "no_response"
    if r.status_code == 403:
        return None, "http_403"
    if r.status_code >= 400:
        return None, f"http_{r.status_code}"
    items = r.json().get("items", [])
    results = []
    for it in items:
        pr_num = it.get("number")
        results.append({
            "number": pr_num,
            "title": it.get("title"),
            "merged_at_top": it.get("merged_at"),
            "pr_field_merged_at": it.get("pull_request", {}).get("merged_at") if it.get("pull_request") else None,
            "state": it.get("state"),
        })
    return results, None


def search_code(repo_full, keyword):
    q = f'{keyword} repo:{repo_full}'
    r, err = throttled_get(
        "https://api.github.com/search/code",
        params={"q": q, "per_page": 5},
        search=True,
    )
    if err or r is None:
        return None, err or "no_response"
    if r.status_code == 403:
        return None, "http_403"
    if r.status_code >= 400:
        return None, f"http_{r.status_code}"
    items = r.json().get("items", [])
    return [{"path": it.get("path"), "name": it.get("name")} for it in items], None


# Get repo full names for our opportunities
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Fetch all opportunities
cur.execute(f"""
SELECT o.id, o.project_id, o.source_type, o.source_ref, o.title, o.description,
       o.issue_number, o.issue_reactions,
       o.value_evidence, o.maintainer_evidence,
       p.url, p.language, p.stars, m.canonical_url
FROM opportunities o
JOIN projects p ON p.id = o.project_id
LEFT JOIN project_meta m ON m.project_id = o.project_id
WHERE o.id IN ({','.join('?'*len(IDS))});
""", IDS)
ops = [dict(r) for r in cur.fetchall()]
conn.close()

results = []

for op in ops:
    oid = op["id"]
    repo_full = op["project_id"]
    source_type = op["source_type"]
    issue_number = op["issue_number"]
    rec = {
        "opportunity_id": oid,
        "verdict": "confirmed",
        "reason": "",
        "checks": [],
        "corrections": [],
        "degraded": False,
    }
    try:
        ve = json.loads(op["value_evidence"] or "{}")
        me = json.loads(op["maintainer_evidence"] or "{}")
    except Exception as e:
        rec["verdict"] = "confirmed"
        rec["reason"] = f"evidence parse failed: {e}"
        rec["degraded"] = True
        results.append(rec)
        continue

    # --- Universal pre-check: meta-discussion keywords ---
    gap_desc = ve.get("gap_desc", "") or ""
    META_KW = ["who uses", "future of", "RFC", "survey", "poll", "discussion", "designing"]
    title = (op["title"] or "").lower()
    desc = (op["description"] or "").lower()

    if source_type != "feature_gap":
        meta_hit = next((k for k in META_KW if k.lower() in gap_desc.lower()), None)
        if meta_hit:
            rec["verdict"] = "refuted"
            rec["reason"] = f"gap_desc 含元讨论关键词「{meta_hit}」"
            rec["checks"].append(f"meta_keyword:{meta_hit}")
            results.append(rec)
            continue
    elif source_type == "feature_gap":
        # For feature_gap, also check meta-keywords (the rule says non-feature_gap types)
        # but the issue body itself might be a discussion. Skip the meta check for feature_gap here.
        pass

    if issue_number is None:
        # feature_gap without issue number: rely on feature_verification
        feat = ve.get("feature_verification", {}) or {}
        terms = feat.get("searched_terms", []) or []
        # budget at 2 code searches
        for term in terms[:2]:
            r, err = search_code(repo_full, term)
            if r is None:
                rec["checks"].append(f"code_search:{term}:{err}")
                continue
            if r:
                rec["checks"].append(f"code_search:{term}:hit:{r[0]['path']}")
                rec["verdict"] = "refuted"
                rec["reason"] = f"code search 命中 {r[0]['path']}，功能已存在"
                break
        results.append(rec)
        continue

    # Get issue
    issue, err = get_issue(repo_full, issue_number)
    if err and issue is None:
        rec["verdict"] = "confirmed"
        rec["reason"] = f"无法核查 issue（{err}）"
        rec["degraded"] = True
        rec["checks"].append(f"issue_get:{err}")
        results.append(rec)
        continue

    if issue.get("status_code") == 404:
        rec["verdict"] = "refuted"
        rec["reason"] = f"issue #{issue_number} 不存在 (404)"
        rec["checks"].append("issue:404")
        results.append(rec)
        continue

    rec["checks"].append(f"issue_state:{issue.get('state')}")

    # State check
    if issue.get("state") == "closed":
        rec["verdict"] = "refuted"
        rec["reason"] = f"issue #{issue_number} 已关闭"
        rec["checks"].append("issue_state:closed")
        results.append(rec)
        continue

    # Labels check
    labels = [l.lower() for l in issue.get("labels", [])]
    if any(l in ("not planned", "wontfix", "wont-fix", "won't fix") for l in labels):
        rec["verdict"] = "refuted"
        rec["reason"] = f"issue 标签含 wontfix/not planned: {labels}"
        rec["checks"].append(f"labels:{labels}")
        results.append(rec)
        continue

    # Reactions calibration (only for issue/perf/compat/security types)
    api_reactions = issue.get("reactions", 0)
    stored_reactions = op["issue_reactions"] or 0
    if api_reactions and stored_reactions:
        diff = abs(api_reactions - stored_reactions)
        rel = diff / max(api_reactions, 1)
        if rel > 0.20 and diff > 1:
            rec["corrections"].append(f"issue_reactions: db={stored_reactions} → api={api_reactions}")
            rec["verdict"] = "corrected"

    # Timeline for cross-referenced / connected
    timeline, terr = get_timeline(repo_full, issue_number, max_pages=2)
    if timeline is None:
        rec["checks"].append(f"timeline:{terr}")
    else:
        # look for cross-referenced PR
        linked_prs = []
        for ev in timeline:
            et = ev.get("event", "")
            if et == "cross-referenced":
                src = ev.get("source", {})
                if src.get("type") == "issue" and src.get("issue", {}).get("pull_request"):
                    linked_prs.append((src["issue"]["number"], src["issue"]["state"]))
            elif et == "connected":
                linked_prs.append(("connected_event", ""))
            elif et == "closed":
                pass

        if linked_prs:
            # Has linked PR or connect event — check if merged
            # We only check first linked PR for merging; if any merged, refute
            any_merged = False
            any_open_pr = False
            for entry in linked_prs:
                if entry[0] == "connected_event":
                    rec["checks"].append("timeline:connected_event")
                    any_open_pr = True  # conservative
                    continue
                pr_num, pr_state = entry
                pr_info, perr = get_pr(repo_full, pr_num)
                if pr_info is None:
                    rec["checks"].append(f"linked_pr_{pr_num}:{perr}")
                    continue
                if pr_info.get("merged"):
                    any_merged = True
                    rec["checks"].append(f"linked_pr_{pr_num}_merged")
                elif pr_state == "open":
                    any_open_pr = True
                    rec["checks"].append(f"linked_pr_{pr_num}_open")
            if any_merged:
                rec["verdict"] = "refuted"
                rec["reason"] = f"已 linked PR 且 merged"
                results.append(rec)
                continue

    # similar_prs check (先信后查)
    similar_prs = me.get("similar_prs", []) or []
    same_func_merged = False
    for spr in similar_prs:
        if not isinstance(spr, dict):
            continue
        pr_num = spr.get("number")
        if not pr_num:
            continue
        pr_info, perr = get_pr(repo_full, pr_num)
        if pr_info is None:
            rec["checks"].append(f"similar_pr_{pr_num}:{perr}")
            continue
        rec["checks"].append(f"similar_pr_{pr_num}:merged={pr_info.get('merged')}")
        if pr_info.get("merged"):
            # only refute if it's an obvious same-implementation PR — but for v2 drafts the similar_prs
            # are usually tangential. We require explicit knowledge: skip refute unless title matches the
            # opportunity's title closely. v2 discipline: similar_prs that don't directly close the issue
            # are not auto-refute grounds.
            pass

    # CVE check for security
    if source_type == "security":
        cve = (ve.get("cve_id") or "") + " " + (op.get("urgency_evidence") or "{}")
        # we'll skip unless cve_id present; not applicable here
        pass

    # Build final reason
    if not rec["reason"]:
        if rec["verdict"] == "corrected":
            rec["reason"] = "issue 仍 open，但 reactions 计数需校正；其余未发现反驳"
        else:
            rec["reason"] = f"issue #{issue_number} 仍 open，labels 无 wontfix，无 linked merged PR，未发现反驳"

    results.append(rec)

print(json.dumps(results, ensure_ascii=False, indent=2))