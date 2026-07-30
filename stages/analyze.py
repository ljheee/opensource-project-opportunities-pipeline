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
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "requests"])
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "pipeline.db")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"
BASE_URL = "https://api.github.com"

# ── HTTP session with resilient retry strategy ─────────────────────────────────
_RETRY_STRATEGY = Retry(
    total=5,
    backoff_factor=1,  # 1s, 2s, 4s, 8s, 16s between retries
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods={"GET", "HEAD", "OPTIONS"},
    raise_on_status=False,
)
_HTTP_ADAPTER = HTTPAdapter(max_retries=_RETRY_STRATEGY)
_SESSION = requests.Session()
_SESSION.mount("https://", _HTTP_ADAPTER)
_SESSION.mount("http://", _HTTP_ADAPTER)

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

_OPP_UPSERT_SQL = """
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
        status=CASE WHEN opportunities.status='refuted' THEN 'refuted' ELSE 'draft' END,
        value=CASE WHEN opportunities.status='refuted' THEN opportunities.value ELSE NULL END,
        difficulty=CASE WHEN opportunities.status='refuted' THEN opportunities.difficulty ELSE NULL END,
        urgency=CASE WHEN opportunities.status='refuted' THEN opportunities.urgency ELSE NULL END,
        maintainer_signal=CASE WHEN opportunities.status='refuted' THEN opportunities.maintainer_signal ELSE NULL END
"""


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def gh_get(path: str, params: dict | None = None, is_search: bool = False):
    """Call GitHub REST API with resilient retry and rate-limit handling.

    Returns (status_code, json_data).
    """
    url = BASE_URL + path if path.startswith("/") else path
    try:
        r = _SESSION.get(url, headers=HEADERS, params=params, timeout=30)
        # Be polite to GitHub: pause between requests; search endpoint is stricter.
        time.sleep(3 if is_search else 2)

        # Manual rate-limit handling based on X-RateLimit-Reset (more precise than backoff).
        if r.status_code in (429, 403):
            reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(1, reset - int(time.time()))
            print(f"  Rate limited, waiting {min(wait, 60)}s...")
            time.sleep(min(wait, 60))
            r = _SESSION.get(url, headers=HEADERS, params=params, timeout=30)

        return r.status_code, r.json() if r.content else {}
    except requests.exceptions.RetryError as e:
        print(f"  Request failed after retries: {e}")
        return 0, {}
    except requests.exceptions.SSLError as e:
        print(f"  SSL error: {e}")
        return 0, {}
    except requests.exceptions.ConnectionError as e:
        print(f"  Connection error: {e}")
        return 0, {}
    except Exception as e:
        print(f"  Request error: {e}")
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


# ── evidence enrichment helpers (toward design.md 5.5) ───────────────────────

_STOP_WORDS = {
    "this", "that", "with", "from", "have", "been", "they", "will", "would",
    "could", "should", "there", "their", "what", "when", "where", "which",
    "while", "about", "after", "before", "being", "between", "both", "into",
    "through", "during", "above", "below", "under", "over", "then", "than",
    "them", "these", "those", "here", "some", "only", "also", "just", "like",
}

_PROD_KEYWORDS = [
    "in production", "production", "prod", "crash", "data loss", "outage",
    "incident", "downtime", "production use", "real world", "real-world",
]

_PERF_KEYWORDS = ["perf", "performance", "bottleneck", "lock", "mutex", "memory",
                  "cpu", "alloc", "allocation", "cache", "slow", "latency", "throughput"]


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text for related-issue matching."""
    words = re.findall(r"[a-z]{4,}", (text or "").lower())
    return {w for w in words if w not in _STOP_WORDS}


def _extract_quote_around_keyword(text: str, keyword: str, window: int = 100) -> str:
    """Return a substring around the first occurrence of keyword."""
    if not text:
        return ""
    idx = text.lower().find(keyword)
    if idx < 0:
        return ""
    start = max(0, idx - window)
    end = min(len(text), idx + len(keyword) + window)
    return text[start:end].strip().replace("\n", " ")


def _extract_prod_signal_quote(body: str, comments: list) -> tuple[str, bool]:
    """Extract a production-signal quote from issue body/comments."""
    for kw in _PROD_KEYWORDS:
        quote = _extract_quote_around_keyword(body or "", kw, 120)
        if quote:
            return quote, True
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        cbody = comment.get("body") or ""
        for kw in _PROD_KEYWORDS:
            quote = _extract_quote_around_keyword(cbody, kw, 120)
            if quote:
                return quote, True
    return "", False


def _count_related_issues(issues: list, title: str, body: str, exclude_number: int | None = None) -> int:
    """Count other issues sharing at least 2 meaningful keywords."""
    current = _extract_keywords(title + " " + (body or ""))
    if not current:
        return 0
    count = 0
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        if exclude_number is not None and issue.get("number") == exclude_number:
            continue
        issue_text = issue.get("title", "") + " " + (issue.get("body") or "")
        issue_words = _extract_keywords(issue_text)
        if len(current & issue_words) >= 2:
            count += 1
    return count


def _find_related_paths(paths: list[str], keyword: str, max_results: int = 5) -> list[str]:
    """Find target paths related to a keyword."""
    if not keyword:
        return []
    keyword_lower = keyword.lower()
    parts = [p for p in keyword_lower.replace("-", "_").replace("/", " ").split() if len(p) > 2]
    related = []
    for p in paths:
        p_lower = p.lower()
        if keyword_lower in p_lower:
            related.append(p)
        elif any(part in p_lower for part in parts):
            related.append(p)
        if len(related) >= max_results:
            break
    return related


def _has_stub(paths: list[str], feature_name: str) -> bool:
    """Check whether target project has any file/dir matching the feature name."""
    fn_lower = feature_name.lower()
    return any(fn_lower in p.lower() for p in paths)


def _find_approach_file(target_paths: list[str], title: str, body: str) -> str:
    """Try to identify a target source file related to an issue."""
    text = (body or "") + " " + title
    # Look for explicit file mentions
    file_pattern = r"(?:^|/)([a-zA-Z0-9_\-/]+\.(?:go|rs|py|ts|js|java|scala|kt|cpp|c|h|hpp))"
    matches = re.findall(file_pattern, text)
    if matches:
        return matches[0]
    # Fallback to keyword matching
    text_lower = text.lower()
    for kw in _PERF_KEYWORDS:
        if kw in text_lower:
            related = _find_related_paths(target_paths, kw, 1)
            if related:
                return related[0]
    return ""


def _make_gap_desc(source_type: str, title: str, body: str | None = None,
                   canonical_url: str | None = None) -> str:
    """Generate a concise gap description for evidence JSON."""
    if source_type == "feature_gap":
        return ("The canonical implementation appears to have this feature, "
                f"but the target project seems missing or incomplete: {title}")
    if source_type == "compatibility":
        return f"Behavior may differ from the canonical implementation: {title}"
    if source_type == "security":
        return f"Potential security concern reported: {title}"
    if source_type == "performance":
        return f"Potential performance issue reported: {title}"
    return f"User-reported issue or requested improvement: {title}"


def _make_why_hard(source_type: str, title: str, body: str | None,
                   has_canonical: bool, approach_file: str = "") -> str:
    """Generate a why_hard hint for difficulty_evidence."""
    text = (title + " " + (body or "")).lower()
    reasons = []
    if any(w in text for w in ["concurrent", "thread", "mutex", "lock", "race", "atomic", "async"]):
        reasons.append("involves concurrency/locking")
    if any(w in text for w in ["core data structure", "data structure", "algorithm", "index"]):
        reasons.append("may require core data structure or algorithm changes")
    if any(w in text for w in ["language limitation", "not supported", "cannot", "unable"]):
        reasons.append("may hit language/platform limitations")
    if source_type == "performance" and approach_file:
        reasons.append(f"likely needs careful profiling/changes around {approach_file}")
    if not has_canonical:
        reasons.append("no canonical reference implementation available for guidance")
    if not reasons:
        return "Implementation effort unclear without deeper investigation."
    return "Hard because: " + "; ".join(reasons)


_REJECT_KEYWORDS = [
    "out of scope", "won't fix", "won’t fix", "wontfix", "wont fix",
    "by design", "not planned", "not in scope", "intentional",
]


def _contains_phrase(text: str, phrase: str) -> bool:
    """Word-boundary aware phrase match."""
    if not text or not phrase:
        return False
    if not phrase.isascii():
        return phrase in text
    pattern = r'(?<!\w)' + re.escape(phrase) + r'(?!\w)'
    return bool(re.search(pattern, text))


def _pr_rejection_comment(project_id: str, pr_number: int) -> str:
    """Fetch PR comments/reviews and look for a maintainer rejection reason."""
    try:
        _, comments = gh_get(f"/repos/{project_id}/issues/{pr_number}/comments", params={"per_page": 20})
        comments = comments if isinstance(comments, list) else []
        _, reviews = gh_get(f"/repos/{project_id}/pulls/{pr_number}/comments", params={"per_page": 20})
        reviews = reviews if isinstance(reviews, list) else []
    except Exception:
        return ""

    for item in comments + reviews:
        if not isinstance(item, dict):
            continue
        author_assoc = item.get("author_association", "")
        if author_assoc not in ("OWNER", "MEMBER", "COLLABORATOR"):
            continue
        body = (item.get("body") or "").lower()
        if any(_contains_phrase(body, kw) for kw in _REJECT_KEYWORDS):
            return (item.get("body") or "").strip()[:250]
    return ""


def _search_similar_prs(project_id: str, title: str) -> list[dict]:
    """Search merged and closed/unmerged PRs related to an issue title."""
    prs = []
    # Use shorter title slice to leave room for search operators
    keyword = title[:40].replace('"', '')

    for state_filter in ["is:merged", "is:closed -is:merged"]:
        search_q = f"repo:{project_id} is:pr {state_filter} {keyword}"
        sc_s, search_res = gh_get("/search/issues", params={"q": search_q, "per_page": 3}, is_search=True)
        if sc_s != 200 or not isinstance(search_res, dict):
            continue
        for item in search_res.get("items", [])[:3]:
            if not isinstance(item, dict):
                continue
            pr_number = item.get("number")
            pr_title = item.get("title", "")
            created = item.get("created_at", "")
            age = None
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    age = (datetime.now(timezone.utc) - dt).days
                except Exception:
                    pass

            merged = state_filter == "is:merged"
            maintainer_comment = ""
            if not merged and pr_number:
                maintainer_comment = _pr_rejection_comment(project_id, pr_number)

            prs.append({
                "number": pr_number,
                "title": pr_title,
                "merged": merged,
                "url": f"https://github.com/{project_id}/pull/{pr_number}" if pr_number else "",
                "age_days": age,
                "maintainer_comment": maintainer_comment,
            })

    return prs[:5]


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

    # 候选窗口取 50（而非 20）：PR 密集的项目里 top-N-by-comments 会被 PR 挤占，
    # 真 issue 挤不进窗口（实测 llama-swap top-20 中 16 个是 PR）。先过滤 PR 再
    # 排序截取，保证候选池里有足够的真 issue。窗口放大不增加请求数（仍 1 次）。
    sc3, issues_raw = gh_get(
        f"/repos/{project_id}/issues",
        params={"state": "open", "sort": "comments", "direction": "desc", "per_page": 50},
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

        similar_prs = _search_similar_prs(project_id, title)

        maintainer_evidence = json.dumps({
            "similar_prs": similar_prs,
            "maintainer_responses": maintainer_responses,
            "welcome_labels": welcome_labels,
        })

        prod_quote, has_prod = _extract_prod_signal_quote(body, comments)
        body_lower = (body or "").lower()
        has_workaround = any(w in body_lower for w in ["workaround", "work around", "as a workaround", "alternatively"])
        cve_id = None
        if source_type == "security":
            cve_m = re.search(r"CVE-\d{4}-\d+", title + " " + body)
            cve_id = cve_m.group(0) if cve_m else None

        issue_count = _count_related_issues(issues, title, body, exclude_number=issue_num)
        gap_desc = _make_gap_desc(source_type, title, body)
        approach_file = _find_approach_file(target_paths, title, body) if source_type == "performance" else ""
        why_hard = _make_why_hard(source_type, title, body, has_canonical=False, approach_file=approach_file)

        value_evidence = json.dumps({
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": reaction_count,
            "issue_count": issue_count,
            "has_workaround": has_workaround,
            "prod_signal_quote": prod_quote,
            "has_prod_signal": has_prod,
            "gap_desc": gap_desc,
        })
        difficulty_evidence = json.dumps({
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": why_hard,
            "target_approach_file": approach_file,
        })
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
        related_files = _find_related_paths(target_paths, feat_name, 5)
        target_has_stub = _has_stub(target_paths, feat_name)
        gap_desc = _make_gap_desc("feature_gap", feat_name)
        why_hard = _make_why_hard("feature_gap", feat_name, "", has_canonical=True)

        merged = False
        for iopp in issue_opportunities:
            if feat_name.lower() in iopp["title"].lower() or feat_name.lower() in iopp["description"].lower():
                ve = json.loads(iopp["value_evidence"])
                ve["canonical_impl_url"] = feat_url
                ve["target_related_files"] = related_files
                ve["target_has_stub"] = target_has_stub
                ve["feature_desc"] = feat_name
                ve["gap_desc"] = gap_desc
                iopp["value_evidence"] = json.dumps(ve)
                de = json.loads(iopp["difficulty_evidence"])
                de["canonical_impl_url"] = feat_url
                de["why_hard"] = why_hard
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
                "value_evidence": json.dumps({
                    "canonical_impl_url": feat_url,
                    "canonical_impl_loc": 0,
                    "peer_impl_urls": [],
                    "issue_reactions": 0,
                    "target_has_stub": target_has_stub,
                    "target_related_files": related_files,
                    "feature_desc": feat_name,
                    "gap_desc": gap_desc,
                }),
                "difficulty_evidence": json.dumps({
                    "canonical_impl_url": feat_url,
                    "canonical_impl_loc": 0,
                    "why_hard": why_hard,
                }),
                "urgency_evidence": json.dumps({
                    "cve_id": None,
                    "has_prod_signal": False,
                    "has_workaround": False,
                }),
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
            conn.execute(_OPP_UPSERT_SQL, (
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

