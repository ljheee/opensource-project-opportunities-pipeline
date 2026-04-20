#!/usr/bin/env python3
"""Stage 4: Deep Analysis Pipeline"""

import sqlite3
import json
import base64
import time
import os
from datetime import datetime, timezone
import requests

DB_PATH = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def api_get(url, params=None, retry=3):
    """GitHub API GET with rate limiting and retry"""
    for attempt in range(retry):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=60)
            if resp.status_code == 403:
                print(f"  API 403, waiting 60s...")
                time.sleep(60)
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            time.sleep(1)
            return resp.json()
        except requests.exceptions.SSLError as e:
            print(f"  SSL error (attempt {attempt+1}/{retry}): {e}")
            if attempt < retry - 1:
                time.sleep(10)
        except requests.exceptions.RequestException as e:
            print(f"  API error: {e}")
            if attempt < retry - 1:
                time.sleep(5)
    return None

def get_repo_info(project_id):
    """Get repository basic info"""
    return api_get(f"https://api.github.com/repos/{project_id}")

def get_readme(project_id):
    """Get README content (base64 decoded)"""
    data = api_get(f"https://api.github.com/repos/{project_id}/readme")
    if data and "content" in data:
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except:
            return ""
    return ""

def get_releases(project_id):
    """Get recent 5 releases"""
    return api_get(f"https://api.github.com/repos/{project_id}/releases", params={"per_page": 5}) or []

def get_issues(project_id):
    """Get top 20 issues by comments, filter out PRs, sort by reactions"""
    data = api_get(
        f"https://api.github.com/repos/{project_id}/issues",
        params={"state": "open", "sort": "comments", "direction": "desc", "per_page": 20}
    ) or []
    # Filter out PRs
    issues = [i for i in data if "pull_request" not in i]
    # Sort by reactions
    issues.sort(key=lambda x: x.get("reactions", {}).get("total_count", 0), reverse=True)
    return issues

def get_tree(project_id):
    """Get repository tree structure"""
    data = api_get(
        f"https://api.github.com/repos/{project_id}/git/trees/HEAD",
        params={"recursive": 1}
    )
    if not data:
        return None
    if data.get("truncated"):
        # Only keep root level items
        data["tree"] = [t for t in data.get("tree", []) if "/" not in t.get("path", "")]
    return data

def has_linked_pr(project_id, issue_number):
    """Check if issue has linked PR via timeline"""
    timeline = api_get(
        f"https://api.github.com/repos/{project_id}/issues/{issue_number}/timeline",
        params={"per_page": 100}
    ) or []
    if len(timeline) == 100:
        return 0  # Conservative: if truncated, assume no linked PR
    for event in timeline:
        event_type = event.get("event", "")
        if event_type == "cross-referenced":
            source = event.get("source", {})
            if source.get("type") == "issue":
                issue = source.get("issue", {})
                if issue.get("pull_request"):
                    return 1
        if event_type == "connected":
            return 1
    return 0

def search_similar_prs(project_id, keyword):
    """Search for similar closed PRs"""
    time.sleep(2)  # Search API rate limit
    q = f'is:pr is:closed repo:{project_id} "{keyword}"'
    data = api_get("https://api.github.com/search/issues", params={"q": q, "per_page": 10})
    if not data:
        # Fallback to pulls API
        pulls = api_get(f"https://api.github.com/repos/{project_id}/pulls", params={"state": "closed", "per_page": 50}) or []
        return [p for p in pulls if keyword.lower() in (p.get("title", "") + (p.get("body") or "")).lower()]
    return data.get("items", [])

def analyze_project(task, conn):
    """Analyze a single project"""
    task_id, project_id, task_type, trigger_reason, url, lang, stars, latest_release, canonical_name, canonical_lang, canonical_url, peer_versions = task
    
    print(f"\n{'='*60}")
    print(f"Analyzing: {project_id} ({lang}, {stars} stars)")
    print(f"Task type: {task_type}")
    
    # Step 1: Mark as running
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET status='running', started_at=? WHERE id=?", (now_iso(), task_id))
    cursor.execute("UPDATE projects SET status='analyzing' WHERE id=? AND status IN ('active', 'bulk_pending')", (project_id,))
    conn.commit()
    
    try:
        # Step 2: Fetch project info
        print("  Fetching repo info...")
        repo_info = get_repo_info(project_id)
        if not repo_info:
            raise Exception("Failed to fetch repo info")
        default_branch = repo_info.get("default_branch", "main")
        
        print("  Fetching README...")
        readme = get_readme(project_id)
        
        print("  Fetching releases...")
        releases = get_releases(project_id)
        
        print("  Fetching issues...")
        issues = get_issues(project_id)
        
        print("  Fetching directory structure...")
        tree = get_tree(project_id)
        
        # Step 3: Fetch canonical info
        canonical_gap = ""
        canonical_readme = ""
        canonical_tree = None
        canonical_default_branch = "main"
        
        if canonical_url and canonical_url.startswith("http") and canonical_url not in ("unknown", "N/A", "—", "-", "null"):
            print(f"  Fetching canonical: {canonical_url}")
            parts = canonical_url.replace("https://github.com/", "").strip("/").split("/")
            if len(parts) >= 2:
                canonical_owner, canonical_repo = parts[0], parts[1]
                canonical_id = f"{canonical_owner}/{canonical_repo}"
                
                canonical_repo_info = get_repo_info(canonical_id)
                if canonical_repo_info:
                    canonical_default_branch = canonical_repo_info.get("default_branch", "main")
                    canonical_readme = get_readme(canonical_id)
                    canonical_tree = get_tree(canonical_id)
                    canonical_gap = f"Canonical: {canonical_name} ({canonical_lang})"
                else:
                    canonical_gap = "canonical_url 无法访问 (404)"
        else:
            canonical_gap = "canonical_url 未知，无法对比"
        
        # Step 4: Peer comparison
        peer_comparison = "—"
        peer_data = []
        if peer_versions and peer_versions not in ("null", "", None):
            try:
                peer_list = json.loads(peer_versions)
                if isinstance(peer_list, list):
                    for peer in peer_list:
                        if isinstance(peer, dict) and peer.get("url"):
                            # WebFetch would go here - simplified
                            peer_data.append({"url": peer.get("url"), "lang": peer.get("language", "unknown")})
                    peer_comparison = f"Found {len(peer_data)} peer versions"
            except json.JSONDecodeError:
                print(f"  WARN: peer_versions JSON parse failed: {peer_versions}")
        
        # Step 5: Source structure analysis
        source_structure = {"root_dirs": [], "key_files": [], "notes": ""}
        if tree and "tree" in tree:
            for item in tree["tree"]:
                path = item.get("path", "")
                item_type = item.get("type", "")
                if "/" not in path:
                    if item_type == "tree":
                        source_structure["root_dirs"].append(path)
                    elif item_type == "blob":
                        source_structure["key_files"].append(path)
        
        # Find feature gaps (Step 5)
        feature_gaps = []
        if canonical_tree and canonical_readme:
            # Simple keyword matching for feature detection
            keywords = ["rate", "limit", "circuit", "breaker", "retry", "timeout", "cache", "metric", "monitor"]
            for item in canonical_tree.get("tree", []):
                path = item.get("path", "").lower()
                for kw in keywords:
                    if kw in path and path.endswith((".java", ".py", ".go", ".rs")):
                        feature_name = path.split("/")[-1].replace(".java", "").replace(".py", "").replace(".go", "").replace(".rs", "")
                        if feature_name:
                            impl_url = f"https://github.com/{canonical_id}/blob/{canonical_default_branch}/{item.get('path', '')}"
                            feature_gaps.append((feature_name, canonical_lang or "Java", impl_url))
                            break
        
        # Step 6: Issue analysis
        opportunities = []
        
        # Process feature gaps first
        existing_refs = set()
        cursor.execute("SELECT source_ref FROM opportunities WHERE project_id=? AND source_type='feature_gap'", (project_id,))
        for row in cursor.fetchall():
            existing_refs.add(row[0])
        
        for feature_name, feat_lang, impl_url in feature_gaps[:5]:  # Limit to 5
            source_ref = f"canonical:{feat_lang}/{feature_name}"
            # Check for duplicate
            if source_ref in existing_refs:
                continue
            
            opportunities.append({
                "source_type": "feature_gap",
                "source_ref": source_ref,
                "title": f"Missing {feature_name} from {feat_lang} canonical",
                "description": f"The canonical {feat_lang} implementation has {feature_name} feature",
                "canonical_status": f"Implemented in {feat_lang}",
                "peer_status": "Unknown",
                "impl_hint": f"Reference: {impl_url}",
                "issue_number": None,
                "issue_reactions": 0,
                "has_linked_pr": 0,
                "value_evidence": {"canonical_impl_url": impl_url, "peer_impl_urls": [], "issue_reactions": 0},
                "difficulty_evidence": {"canonical_impl_url": impl_url, "canonical_impl_loc": 0, "why_hard": ""},
                "urgency_evidence": {"cve_id": None, "has_prod_signal": False, "has_workaround": False},
                "maintainer_evidence": {"similar_prs": [], "maintainer_responses": [], "welcome_labels": []}
            })
        
        # Process issues
        for issue in issues[:10]:  # Top 10 issues
            issue_number = issue.get("number")
            title = issue.get("title", "")
            body = issue.get("body", "") or ""
            reactions = issue.get("reactions", {}).get("total_count", 0)
            labels = [l.get("name", "").lower() for l in issue.get("labels", [])]
            
            # Skip if linked PR
            print(f"  Checking linked PR for issue #{issue_number}...")
            linked = has_linked_pr(project_id, issue_number)
            if linked:
                print(f"    Skipping issue #{issue_number} - has linked PR")
                continue
            
            # Determine source_type
            source_type = "issue"
            if any("security" in l for l in labels) or "security" in title.lower():
                source_type = "security"
            elif any("performance" in l for l in labels) or "performance" in title.lower():
                source_type = "performance"
            elif any(l in ("bug", "bugfix") for l in labels):
                source_type = "issue"
            
            # Check for maintainer comments
            maintainer_responses = []
            welcome_labels = []
            
            if any(l in ("help wanted", "good first issue") for l in labels):
                welcome_labels = [l for l in labels if l in ("help wanted", "good first issue")]
            
            # Similar PRs search
            keywords = title.lower().replace(":", "").replace(",", "").split()[:2]
            keyword = "-".join(keywords) if keywords else "feature"
            similar_prs = search_similar_prs(project_id, keyword) or []

            similar_pr_list = []
            for pr in similar_prs[:3]:
                pr_merged_at = pr.get("pull_request", {}).get("merged_at") if "pull_request" in pr else pr.get("merged_at")
                if pr_merged_at:
                    merged_dt = datetime.fromisoformat(pr_merged_at.replace("Z", "+00:00"))
                    age_days = (datetime.now(timezone.utc) - merged_dt).days
                    similar_pr_list.append({"merged": True, "age_days": age_days, "maintainer_comment": ""})
            
            issue_url = f"https://github.com/{project_id}/issues/{issue_number}"
            
            opportunities.append({
                "source_type": source_type,
                "source_ref": issue_url,
                "title": title[:200],
                "description": body[:500] if body else title[:200],
                "canonical_status": "Unknown",
                "peer_status": "Unknown",
                "impl_hint": "",
                "issue_number": issue_number,
                "issue_reactions": reactions,
                "has_linked_pr": linked,
                "value_evidence": {"canonical_impl_url": "", "peer_impl_urls": [], "issue_reactions": reactions},
                "difficulty_evidence": {"canonical_impl_url": "", "canonical_impl_loc": 0, "why_hard": ""},
                "urgency_evidence": {"cve_id": None, "has_prod_signal": False, "has_workaround": False},
                "maintainer_evidence": {"similar_prs": similar_pr_list, "maintainer_responses": maintainer_responses, "welcome_labels": welcome_labels}
            })
        
        # Step 7: Write results
        print(f"  Writing {len(opportunities)} opportunities...")
        
        # Calculate overall score
        value_scores = []
        for opp in opportunities:
            ve = opp["value_evidence"]
            if ve.get("canonical_impl_url") and ve.get("issue_reactions", 0) >= 5:
                value_scores.append(7)  # high
            elif ve.get("canonical_impl_url"):
                value_scores.append(5)  # medium
            else:
                value_scores.append(3)  # low
        
        if value_scores:
            overall_score = max(1, min(10, max(value_scores)))
        else:
            overall_score = 5
        
        # Insert/update analysis
        cursor.execute(
            "SELECT COUNT(*) FROM analyses WHERE project_id=? AND task_id=?",
            (project_id, task_id)
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                """INSERT INTO analyses (project_id, task_id, analyzed_at, release_version,
                    source_structure, canonical_gap, peer_comparison, overall_score)
                    VALUES (?,?,?,?,?,?,?,?)""",
                (project_id, task_id, now_iso(), latest_release,
                 json.dumps(source_structure), canonical_gap, peer_comparison, overall_score)
            )
        else:
            cursor.execute(
                """UPDATE analyses SET analyzed_at=?, release_version=?, source_structure=?,
                    canonical_gap=?, peer_comparison=?, overall_score=?
                    WHERE project_id=? AND task_id=?""",
                (now_iso(), latest_release, json.dumps(source_structure),
                 canonical_gap, peer_comparison, overall_score, project_id, task_id)
            )
        
        # Insert/update opportunities
        for opp in opportunities:
            cursor.execute(
                """SELECT COUNT(*) FROM opportunities
                    WHERE project_id=? AND source_type=? AND source_ref=?""",
                (project_id, opp["source_type"], opp["source_ref"])
            )
            now = now_iso()
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    """INSERT INTO opportunities
                        (project_id, task_id, source_type, source_ref, title, description,
                         canonical_status, peer_status, impl_hint, issue_number, issue_reactions,
                         has_linked_pr, value_evidence, difficulty_evidence, urgency_evidence,
                         maintainer_evidence, status, first_seen_at, last_seen_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (project_id, task_id, opp["source_type"], opp["source_ref"],
                     opp["title"], opp["description"], opp["canonical_status"],
                     opp["peer_status"], opp["impl_hint"], opp["issue_number"],
                     opp["issue_reactions"], opp["has_linked_pr"],
                     json.dumps(opp["value_evidence"]),
                     json.dumps(opp["difficulty_evidence"]),
                     json.dumps(opp["urgency_evidence"]),
                     json.dumps(opp["maintainer_evidence"]),
                     "open", now, now)
                )
            else:
                cursor.execute(
                    """UPDATE opportunities SET
                        title=?, description=?, canonical_status=?, peer_status=?,
                        impl_hint=?, issue_number=?, issue_reactions=?, has_linked_pr=?,
                        task_id=?, value_evidence=?, difficulty_evidence=?,
                        urgency_evidence=?, maintainer_evidence=?,
                        value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL,
                        status='open', last_seen_at=?
                        WHERE project_id=? AND source_type=? AND source_ref=?""",
                    (opp["title"], opp["description"], opp["canonical_status"],
                     opp["peer_status"], opp["impl_hint"], opp["issue_number"],
                     opp["issue_reactions"], opp["has_linked_pr"], task_id,
                     json.dumps(opp["value_evidence"]),
                     json.dumps(opp["difficulty_evidence"]),
                     json.dumps(opp["urgency_evidence"]),
                     json.dumps(opp["maintainer_evidence"]),
                     now, project_id, opp["source_type"], opp["source_ref"])
                )
        
        # Mark done
        cursor.execute("UPDATE tasks SET status='done', finished_at=? WHERE id=?", (now_iso(), task_id))
        cursor.execute(
            """UPDATE projects SET status='active',
                prev_stars=COALESCE(stars, prev_stars),
                prev_open_issues=COALESCE(open_issues, prev_open_issues)
                WHERE id=? AND status='analyzing'""",
            (project_id,)
        )
        conn.commit()
        print(f"  Done: {len(opportunities)} opportunities")
        
    except Exception as e:
        print(f"  ERROR: {e}")
        # Rollback
        cursor.execute("UPDATE tasks SET status='skipped' WHERE id=?", (task_id,))
        if task_type in ("triggered", "incremental"):
            cursor.execute("UPDATE projects SET status='active' WHERE id=? AND status='analyzing'", (project_id,))
        else:
            cursor.execute("UPDATE projects SET status='bulk_pending' WHERE id=? AND status='analyzing'", (project_id,))
        conn.commit()

def main():
    print("Stage 4: Deep Analysis Pipeline")
    print(f"DB: {DB_PATH}")
    print(f"GitHub Token: {'Yes' if GITHUB_TOKEN else 'No (limited)'}")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get pending tasks
    cursor.execute("""
        SELECT t.id, t.project_id, t.task_type, t.trigger_reason,
               p.url, p.language, p.stars, p.latest_release,
               m.canonical_name, m.canonical_lang, m.canonical_url, m.peer_versions
        FROM tasks t
        JOIN projects p ON p.id = t.project_id
        LEFT JOIN project_meta m ON m.project_id = t.project_id
        WHERE t.task_date = '2026-04-20' AND t.status IN ('pending', 'running')
        ORDER BY CASE t.task_type WHEN 'triggered' THEN 0 WHEN 'incremental' THEN 1 ELSE 2 END,
                 p.stars DESC
    """)
    tasks = cursor.fetchall()
    print(f"\nFound {len(tasks)} tasks to analyze")
    
    for task in tasks:
        analyze_project(task, conn)
    
    conn.close()
    print("\nStage 4 complete!")

if __name__ == "__main__":
    main()
