#!/usr/bin/env python3
"""Stage 4 v2: Generic rule-based analyzer.

Reads pending/running tasks from the DB, fetches GitHub data, applies simple
heuristics, and writes DRAFT opportunities (status='draft').

Complex judgment is intentionally left to the LLM via prompts/analyze_v2.md.
"""
from __future__ import annotations
import argparse
import base64
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "requests"])
    import requests

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "pipeline.db")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"
BASE_URL = "https://api.github.com"

MAX_ISSUES = 15
MAX_OPPORTUNITIES = 10
MAX_FEATURE_GAPS = 5

SKIP_DIRS = {
    "test", "tests", "testdata", "vendor", "node_modules", ".github",
    "docs", "doc", "examples", "example", "scripts", "hack",
    "build", "dist", "target", ".git", "ci", "tools", "tool",
}

KEY_FILES = [
    "go.mod", "go.sum", "Cargo.toml", "setup.py", "requirements.txt",
    "pom.xml", "build.gradle", "package.json", "README.md", "Makefile",
    "Dockerfile", ".github/workflows",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def gh_get(path: str, params: dict | None = None, is_search: bool = False):
    """Call GitHub REST API with rate-limit retry. Returns (status_code, json_data)."""
    url = BASE_URL + path if path.startswith("/") else path
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
            if is_search:
                time.sleep(2)
            else:
                time.sleep(1)
            if r.status_code in (429, 403):
                reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(1, reset - int(time.time()))
                print(f"  Rate limited, waiting {min(wait, 60)}s...")
                time.sleep(min(wait, 60))
                continue
            return r.status_code, r.json() if r.content else {}
        except Exception as e:
            print(f"  Request error: {e}")
            time.sleep(2)
    return 0, {}


def decode_readme(data: dict) -> str:
    if isinstance(data, dict) and "content" in data:
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            return ""
    return ""


def parse_owner_repo(url: str):
    """Parse owner/repo from a GitHub URL."""
    if not url or not url.startswith("http"):
        return None, None
    m = re.search(r"github\.com/([^/]+)/([^/&#?]+)", url)
    if m:
        return m.group(1), m.group(2).rstrip(".git")
    return None, None


def get_tree_paths(tree_data: dict) -> list[str]:
    """Extract file paths from GitHub tree response."""
    if not isinstance(tree_data, dict):
        return []
    items = tree_data.get("tree", [])
    if tree_data.get("truncated"):
        return [i["path"] for i in items if isinstance(i, dict) and "/" not in i.get("path", "")]
    return [i["path"] for i in items if isinstance(i, dict)]


def get_root_dirs(paths: list[str]) -> list[str]:
    dirs = set()
    for p in paths:
        parts = p.split("/")
        if len(parts) > 1:
            dirs.add(parts[0])
        elif "." not in p:
            dirs.add(p)
    return sorted(dirs)


def get_key_files(paths: list[str]) -> list[str]:
    key = []
    for imp in KEY_FILES:
        for p in paths:
            if p == imp or p.endswith("/" + imp):
                key.append(p)
                break
    return key[:10]


def is_canonical_unknown(url: str | None) -> bool:
    if not url:
        return True
    u = url.strip().lower()
    return not u.startswith("http")


def find_feature_gaps(target_paths: list[str], canonical_paths: list[str],
                       canonical_owner: str, canonical_repo: str,
                       canonical_lang: str, default_branch: str):
    """Compare target and canonical trees to find missing features."""
    gaps = []
    target_dirs = set(get_root_dirs(target_paths))
    canonical_dirs = set(get_root_dirs(canonical_paths))

    for d in sorted(canonical_dirs):
        if d.lower() in SKIP_DIRS:
            continue
        dl = d.lower()
        has_match = any(
            td.lower() == dl or dl in td.lower() or td.lower() in dl
            for td in target_dirs
        )
        if not has_match and len(d) > 2:
            impl_url = f"https://github.com/{canonical_owner}/{canonical_repo}/tree/{default_branch}/{d}"
            gaps.append((d, canonical_lang, impl_url))
    return gaps[:MAX_FEATURE_GAPS]


def check_has_linked_pr(timeline_events: list) -> bool:
    """Check if issue has a linked pull request."""
    for event in timeline_events:
        if not isinstance(event, dict):
            continue
        if event.get("event") in ("cross-referenced", "connected"):
            src = event.get("source", {}) or {}
            issue_data = src.get("issue", {}) or {}
            if "pull_request" in issue_data:
                return True
    return False


def classify_issue(title: str, body: str | None) -> str:
    """Classify issue type by simple keyword matching."""
    text = (title + " " + (body or "")).lower()
    if any(w in text for w in ["cve", "security", "vulnerability", "xss", "injection", "auth", "csrf", "exploit"]):
        return "security"
    if any(w in text for w in ["perf", "performance", "slow", "latency", "memory", "cpu", "throughput", "bottleneck"]):
        return "performance"
    if any(w in text for w in ["compat", "compatibility", "breaking", "migration", "upgrade", "version", "deprecat"]):
        return "compatibility"
    return "issue"


def _rollback_task(conn: sqlite3.Connection, task_id: int, project_id: str, task_type: str):
    """Mark task skipped and return project to appropriate queue."""
    conn.execute("UPDATE tasks SET status='skipped', finished_at=? WHERE id=?", (now_utc(), task_id))
    if task_type in ("triggered", "incremental"):
        conn.execute("UPDATE projects SET status='active' WHERE id=? AND status='analyzing'", (project_id,))
    else:
        conn.execute("UPDATE projects SET status='bulk_pending' WHERE id=? AND status='analyzing'", (project_id,))
    conn.commit()


def _task_success(conn: sqlite3.Connection, task_id: int):
    """Mark task as analyzed (CLI will later mark done)."""
    conn.execute("UPDATE tasks SET status='analyzed' WHERE id=?", (task_id,))
    conn.commit()


def _estimate_overall_score(opportunities: list[dict]) -> int:
    """Rough score 1-10 based on the best draft opportunity value."""
    if not opportunities:
        return 3
    best = "low"
    for opp in opportunities:
        ve = json.loads(opp.get("value_evidence") or "{}")
        has_canonical = bool(ve.get("canonical_impl_url"))
        reactions = int(ve.get("issue_reactions") or 0)
        me = json.loads(opp.get("maintainer_evidence") or "{}")
        welcoming = bool(me.get("welcome_labels"))
        if has_canonical and (reactions >= 5 or welcoming):
            best = "high"
            break
        elif has_canonical or reactions >= 5 or welcoming:
            best = "medium"
    return {"high": 7, "medium": 5, "low": 3}.get(best, 3)


def analyze_project(conn: sqlite3.Connection, task: dict, dry_run: bool = False) -> int:
    task_id = task["task_id"]
    project_id = task["project_id"]
    task_type = task["task_type"]
    canonical_url = task["canonical_url"]

    print(f"\n[{task_id}] {project_id}")

    if dry_run:
        print("  dry-run: skipping API calls and DB state changes")
        return 0

    # Step 1: mark running
    conn.execute("UPDATE tasks SET status='running', started_at=? WHERE id=?", (now_utc(), task_id))
    conn.execute("UPDATE projects SET status='analyzing' WHERE id=? AND status IN ('active','bulk_pending')", (project_id,))
    conn.commit()

    owner, repo = project_id.split("/", 1)

    # Step 2: target project info
    sc, readme_data = gh_get(f"/repos/{project_id}/readme")
    if sc not in (200, 404):
        print(f"  ERROR: README fetch failed ({sc})")
        _rollback_task(conn, task_id, project_id, task_type)
        return 0
    readme_text = decode_readme(readme_data) if sc == 200 else ""

    sc2, releases = gh_get(f"/repos/{project_id}/releases", params={"per_page": 5})
    if sc2 not in (200, 404):
        print(f"  ERROR: releases fetch failed ({sc2})")
        _rollback_task(conn, task_id, project_id, task_type)
        return 0
    releases = releases if isinstance(releases, list) else []
    latest_release = releases[0].get("tag_name", "") if releases else ""

    sc3, issues_raw = gh_get(
        f"/repos/{project_id}/issues",
        params={"state": "open", "sort": "comments", "direction": "desc", "per_page": 20},
    )
    if sc3 not in (200, 404):
        print(f"  ERROR: issues fetch failed ({sc3})")
        _rollback_task(conn, task_id, project_id, task_type)
        return 0
    issues_raw = issues_raw if isinstance(issues_raw, list) else []
    issues = [i for i in issues_raw if isinstance(i, dict) and "pull_request" not in i]
    issues.sort(key=lambda x: (x.get("reactions") or {}).get("total_count", 0) if isinstance(x.get("reactions"), dict) else 0, reverse=True)

    sc4, tree_data = gh_get(f"/repos/{project_id}/git/trees/HEAD", params={"recursive": 1})
    if sc4 not in (200, 404):
        print(f"  ERROR: tree fetch failed ({sc4})")
        _rollback_task(conn, task_id, project_id, task_type)
        return 0
    target_paths = get_tree_paths(tree_data) if sc4 == 200 else []
    source_structure = json.dumps({
        "root_dirs": get_root_dirs(target_paths),
        "key_files": get_key_files(target_paths),
        "notes": "",
    })

    # Step 3: canonical info
    canonical_gap = "canonical_url 未知，无法对比"
    peer_comparison = "—"
    feature_gaps = []
    canonical_default_branch = "main"
    canonical_lang = task["canonical_lang"] or "Java"

    if not is_canonical_unknown(canonical_url):
        can_owner, can_repo = parse_owner_repo(canonical_url)
        if can_owner and can_repo:
            sc_repo, repo_info = gh_get(f"/repos/{can_owner}/{can_repo}")
            if sc_repo == 404:
                canonical_gap = "canonical_url 无法访问 (404)"
            elif sc_repo != 200:
                canonical_gap = f"canonical_url API 错误 ({sc_repo})"
            else:
                canonical_default_branch = repo_info.get("default_branch", "main")
                canonical_lang = repo_info.get("language", canonical_lang)
                _, can_readme_data = gh_get(f"/repos/{can_owner}/{can_repo}/readme")
                _, can_tree = gh_get(f"/repos/{can_owner}/{can_repo}/git/trees/HEAD", params={"recursive": 1})
                canonical_paths = get_tree_paths(can_tree)
                feature_gaps = find_feature_gaps(
                    target_paths, canonical_paths,
                    can_owner, can_repo, canonical_lang, canonical_default_branch,
                )
                canonical_gap = f"Compared with {can_owner}/{can_repo}: {len(feature_gaps)} potential missing features"
                peer_comparison = f"Canonical ({canonical_lang}): {can_owner}/{can_repo}"

    # Step 4: peer versions (fetch trees only)
    peer_versions = []
    if task["peer_versions"]:
        try:
            peer_versions = json.loads(task["peer_versions"])
            if isinstance(peer_versions, list):
                for peer in peer_versions:
                    if isinstance(peer, dict) and peer.get("url"):
                        p_owner, p_repo = parse_owner_repo(peer["url"])
                        if p_owner and p_repo:
                            _, p_tree = gh_get(f"/repos/{p_owner}/{p_repo}/git/trees/HEAD", params={"recursive": 1})
                            peer["tree_paths"] = get_tree_paths(p_tree)
        except json.JSONDecodeError:
            peer_versions = []

    # Step 5/6: issue analysis
    issue_opportunities = []
    for issue in issues[:MAX_ISSUES]:
        issue_num = issue.get("number")
        title = issue.get("title", "")
        body = issue.get("body") or ""
        reactions_obj = issue.get("reactions") or {}
        reaction_count = reactions_obj.get("total_count", 0) if isinstance(reactions_obj, dict) else 0
        labels = [l.get("name", "") for l in (issue.get("labels") or []) if isinstance(l, dict)]

        _, timeline = gh_get(f"/repos/{project_id}/issues/{issue_num}/timeline", params={"per_page": 100})
        timeline = timeline if isinstance(timeline, list) else []
        if check_has_linked_pr(timeline):
            continue

        source_type = classify_issue(title, body)

        welcome_labels = [l for l in labels if l.lower() in {"help wanted", "help-wanted", "good first issue", "good-first-issue"}]
        _, comments = gh_get(f"/repos/{project_id}/issues/{issue_num}/comments", params={"per_page": 50})
        comments = comments if isinstance(comments, list) else []
        maintainer_responses = []
        for comment in comments[:10]:
            if not isinstance(comment, dict):
                continue
            if comment.get("author_association") in ("OWNER", "MEMBER", "COLLABORATOR"):
                maintainer_responses.append({"body_quote": (comment.get("body") or "")[:200]})
            if len(maintainer_responses) >= 2:
                break

        similar_prs = []
        search_q = f"repo:{project_id} is:pr is:merged {title[:50]}"
        sc_s, search_res = gh_get("/search/issues", params={"q": search_q, "per_page": 3}, is_search=True)
        if sc_s == 200 and isinstance(search_res, dict):
            for item in search_res.get("items", [])[:3]:
                if isinstance(item, dict):
                    created = item.get("created_at", "")
                    age = None
                    if created:
                        try:
                            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                            age = (datetime.now(timezone.utc) - dt).days
                        except Exception:
                            pass
                    similar_prs.append({"title": item.get("title", ""), "merged": True, "age_days": age, "maintainer_comment": ""})

        maintainer_evidence = json.dumps({
            "similar_prs": similar_prs,
            "maintainer_responses": maintainer_responses,
            "welcome_labels": welcome_labels,
        })

        value_evidence = json.dumps({
            "canonical_impl_url": "",
            "peer_impl_urls": [],
            "issue_reactions": reaction_count,
        })
        difficulty_evidence = json.dumps({
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": "",
        })
        cve_id = None
        if source_type == "security":
            cve_m = re.search(r"CVE-\d{4}-\d+", title + " " + body)
            cve_id = cve_m.group(0) if cve_m else None
        body_lower = (body or "").lower()
        has_prod = any(w in body_lower for w in ["production", "prod", "crash", "data loss", "outage"])
        has_workaround = any(w in body_lower for w in ["workaround", "work around", "as a workaround", "alternatively"])
        urgency_evidence = json.dumps({
            "cve_id": cve_id,
            "has_prod_signal": has_prod,
            "has_workaround": has_workaround,
        })

        issue_opportunities.append({
            "source_type": source_type,
            "source_ref": f"issue:{issue_num}",
            "title": title[:200],
            "description": body[:500],
            "issue_number": issue_num,
            "issue_reactions": reaction_count,
            "value_evidence": value_evidence,
            "difficulty_evidence": difficulty_evidence,
            "urgency_evidence": urgency_evidence,
            "maintainer_evidence": maintainer_evidence,
            "impl_hint": f"GitHub Issue #{issue_num}: {title[:100]}",
        })

    # Step 5: feature_gap opportunities
    feature_gap_opportunities = []
    for feat_name, feat_lang, feat_url in feature_gaps:
        merged = False
        for iopp in issue_opportunities:
            if feat_name.lower() in iopp["title"].lower() or feat_name.lower() in iopp["description"].lower():
                ve = json.loads(iopp["value_evidence"])
                ve["canonical_impl_url"] = feat_url
                iopp["value_evidence"] = json.dumps(ve)
                de = json.loads(iopp["difficulty_evidence"])
                de["canonical_impl_url"] = feat_url
                iopp["difficulty_evidence"] = json.dumps(de)
                merged = True
                break
        if not merged:
            feature_gap_opportunities.append({
                "source_type": "feature_gap",
                "source_ref": f"canonical:{feat_lang}/{feat_name}",
                "title": f"Missing feature: {feat_name} (exists in {feat_lang} canonical)",
                "description": f"The canonical {feat_lang} implementation has a '{feat_name}' module/feature that appears missing or incomplete here.",
                "issue_number": None,
                "issue_reactions": 0,
                "value_evidence": json.dumps({"canonical_impl_url": feat_url, "peer_impl_urls": [], "issue_reactions": 0}),
                "difficulty_evidence": json.dumps({"canonical_impl_url": feat_url, "canonical_impl_loc": 0, "why_hard": ""}),
                "urgency_evidence": json.dumps({"cve_id": None, "has_prod_signal": False, "has_workaround": False}),
                "maintainer_evidence": json.dumps({"similar_prs": [], "maintainer_responses": [], "welcome_labels": []}),
                "impl_hint": f"See canonical implementation: {feat_url}",
            })

    all_opportunities = (feature_gap_opportunities + issue_opportunities)[:MAX_OPPORTUNITIES]
    overall_score = _estimate_overall_score(all_opportunities)

    # Step 7: write analyses/opportunities
    analyzed_at = now_utc()
    conn.execute("""
        INSERT INTO analyses (project_id, task_id, analyzed_at, release_version,
                              source_structure, canonical_gap, peer_comparison, overall_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, task_id) DO UPDATE SET
            analyzed_at=excluded.analyzed_at,
            release_version=excluded.release_version,
            source_structure=excluded.source_structure,
            canonical_gap=excluded.canonical_gap,
            peer_comparison=excluded.peer_comparison,
            overall_score=excluded.overall_score
    """, (project_id, task_id, analyzed_at, latest_release,
          source_structure, canonical_gap, peer_comparison, overall_score))

    opp_count = 0
    for opp in all_opportunities:
        try:
            conn.execute("""
                INSERT INTO opportunities
                    (project_id, task_id, source_type, source_ref, title, description,
                     value, difficulty, urgency, maintainer_signal,
                     impl_hint, issue_number, issue_reactions, has_linked_pr,
                     value_evidence, difficulty_evidence, urgency_evidence, maintainer_evidence,
                     status, first_seen_at, last_seen_at)
                VALUES
                    (?, ?, ?, ?, ?, ?,
                     NULL, NULL, NULL, NULL,
                     ?, ?, ?, 0,
                     ?, ?, ?, ?,
                     'draft', ?, ?)
                ON CONFLICT(project_id, source_type, source_ref) DO UPDATE SET
                    task_id=excluded.task_id,
                    title=excluded.title,
                    description=excluded.description,
                    impl_hint=excluded.impl_hint,
                    issue_number=excluded.issue_number,
                    issue_reactions=excluded.issue_reactions,
                    value_evidence=excluded.value_evidence,
                    difficulty_evidence=excluded.difficulty_evidence,
                    urgency_evidence=excluded.urgency_evidence,
                    maintainer_evidence=excluded.maintainer_evidence,
                    last_seen_at=excluded.last_seen_at,
                    status='draft',
                    value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
            """, (
                project_id, task_id,
                opp["source_type"], opp["source_ref"], opp["title"], opp["description"],
                opp["impl_hint"], opp["issue_number"], opp["issue_reactions"],
                opp["value_evidence"], opp["difficulty_evidence"],
                opp["urgency_evidence"], opp["maintainer_evidence"],
                analyzed_at, analyzed_at,
            ))
            opp_count += 1
        except Exception as e:
            print(f"    Opportunity insert error: {e}")

    _task_success(conn, task_id)
    print(f"  Written {opp_count} draft opportunities")
    return opp_count


def main():
    parser = argparse.ArgumentParser(description="Stage 4 v2: rule-based draft analyzer")
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        help="Task date to process (YYYY-MM-DD)")
    parser.add_argument("--task-ids", default="",
                        help="Comma-separated task IDs to process; if empty, all pending/running tasks for the date")
    parser.add_argument("--max-projects", type=int, default=None,
                        help="Maximum number of projects to process")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without API calls or DB writes")
    args = parser.parse_args()

    print(f"Stage 4 v2 Analysis starting at {now_utc()} for date {args.date}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT t.id as task_id, t.project_id, t.task_type, t.trigger_reason,
               p.url, p.language, p.stars, p.latest_release,
               m.canonical_name, m.canonical_lang, m.canonical_url, m.peer_versions
        FROM tasks t
        JOIN projects p ON p.id = t.project_id
        LEFT JOIN project_meta m ON m.project_id = t.project_id
        WHERE t.task_date = ?
          AND t.status IN ('pending', 'running')
    """
    params = [args.date]

    if args.task_ids:
        ids = [int(x.strip()) for x in args.task_ids.split(",") if x.strip().isdigit()]
        if ids:
            placeholders = ",".join("?" * len(ids))
            query += f" AND t.id IN ({placeholders})"
            params.extend(ids)

    query += " ORDER BY CASE t.task_type WHEN 'triggered' THEN 0 WHEN 'incremental' THEN 1 ELSE 2 END, p.stars DESC"

    if args.max_projects:
        query += " LIMIT ?"
        params.append(args.max_projects)

    tasks = [dict(row) for row in conn.execute(query, params).fetchall()]
    print(f"Processing {len(tasks)} tasks")

    total_opps = 0
    try:
        for task in tasks:
            try:
                n = analyze_project(conn, task, dry_run=args.dry_run)
                total_opps += n
            except Exception as e:
                print(f"ERROR on [{task['task_id']}] {task['project_id']}: {e}")
                import traceback
                traceback.print_exc()
                try:
                    _rollback_task(conn, task["task_id"], task["project_id"], task["task_type"])
                except Exception as e2:
                    print(f"  Rollback error: {e2}")
    finally:
        conn.close()

    print(f"\nAnalysis complete. Draft opportunities: {total_opps}")


if __name__ == "__main__":
    main()

