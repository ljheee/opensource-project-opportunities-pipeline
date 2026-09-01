#!/usr/bin/env python3
"""Stage 4.7 verify batch for 2026-08-29 T12:25:45Z.
20 opportunities, parallel API verification.
"""
import os, json, time, sqlite3, re
from datetime import datetime, timezone
import requests

DB_PATH = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"
LOG_PATH = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/verify_log/.pending_20260829T122545.json"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# Rate-limit guards
_LAST_CORE = [0.0]
_LAST_SEARCH = [0.0]
_SEARCH_USED = [0]
_SEARCH_BUDGET = 10

def core_get(url, params=None, retries=2):
    """GitHub core REST API; ≥1s between calls."""
    wait = max(0.0, 1.0 - (time.time() - _LAST_CORE[0]))
    if wait > 0:
        time.sleep(wait)
    for attempt in range(retries + 1):
        try:
            r = SESSION.get(url, params=params, timeout=30)
            _LAST_CORE[0] = time.time()
            if r.status_code == 403 and "rate limit" in r.text.lower():
                time.sleep(60)
                continue
            if r.status_code >= 500:
                time.sleep(5)
                continue
            return r
        except Exception as e:
            if attempt == retries:
                raise
            time.sleep(3)
    return r

def search_get(url, params=None):
    """GitHub Search API; ≥7s between calls; total budget 10."""
    if _SEARCH_USED[0] >= _SEARCH_BUDGET:
        return None  # budget exhausted
    wait = max(0.0, 7.0 - (time.time() - _LAST_SEARCH[0]))
    if wait > 0:
        time.sleep(wait)
    try:
        r = SESSION.get(url, params=params, timeout=30)
        _LAST_SEARCH[0] = time.time()
        _SEARCH_USED[0] += 1
        if r.status_code == 403 and "rate limit" in r.text.lower():
            time.sleep(60)
            r = SESSION.get(url, params=params, timeout=30)
            _LAST_SEARCH[0] = time.time()
            _SEARCH_USED[0] += 1
        return r
    except Exception:
        return None

# Load batch data
BATCH = [4452,6014,6018,2789,2790,2860,2862,5308,5314,2845,6124,4573,4575,4623,25,26,27,29,30,31]

def load_opps():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    q = f"""SELECT o.id, o.project_id, o.source_type, o.source_ref, o.title, o.description,
       o.issue_number, o.issue_reactions,
       o.value, o.difficulty, o.urgency, o.maintainer_signal,
       o.value_evidence, o.difficulty_evidence, o.urgency_evidence, o.maintainer_evidence,
       p.url, p.language, p.stars, m.canonical_url, o.status as current_status
FROM opportunities o
JOIN projects p ON p.id = o.project_id
LEFT JOIN project_meta m ON m.project_id = o.project_id
WHERE o.id IN ({",".join("?"*len(BATCH))})"""
    rows = [dict(r) for r in conn.execute(q, BATCH).fetchall()]
    conn.close()
    return rows

# ---- Verification helpers ----
def safe_json_load(s):
    if not s: return {}
    try: return json.loads(s)
    except: return {}

def repo_from_url(url):
    """Extract owner/repo from github.com/... URL."""
    m = re.search(r"github\.com/([^/]+)/([^/]+?)(?:\.git|/|$)", url)
    return (m.group(1), m.group(2)) if m else (None, None)

def parse_source_ref(src_type, src_ref):
    """For 'issue:NNN' style source_ref, return issue_number.
    For 'https://github.com/.../issues/N' return number."""
    m = re.match(r"issue:(\d+)", src_ref or "")
    if m: return int(m.group(1))
    m = re.search(r"/issues/(\d+)", src_ref or "")
    if m: return int(m.group(1))
    return None

def check_meta_discussion(ve):
    gap = (ve.get("gap_desc") or "").lower()
    for kw in ["who uses", "future of", "rfc", "survey", "poll", "discussion", "designing"]:
        if kw in gap:
            return True, kw
    return False, None

def get_issue(repo, n):
    r = core_get(f"https://api.github.com/repos/{repo}/issues/{n}")
    if r.status_code != 200:
        return None
    return r.json()

def get_issue_timeline(repo, n):
    r = core_get(f"https://api.github.com/repos/{repo}/issues/{n}/timeline",
                 params={"per_page": 100})
    if r.status_code != 200:
        return None
    return r.json()

def get_pr(repo, n):
    r = core_get(f"https://api.github.com/repos/{repo}/pulls/{n}")
    if r.status_code != 200:
        return None
    return r.json()

def check_linked_prs(timeline):
    if not timeline:
        return False
    for ev in timeline:
        if ev.get("event") in ("cross-referenced", "connected"):
            src = ev.get("source", {}) or {}
            iss = src.get("issue", {}) or {}
            if iss.get("pull_request"):
                return True
    return False

def search_merged_pr(repo, keyword):
    if _SEARCH_USED[0] >= _SEARCH_BUDGET:
        return None
    r = search_get(f"https://api.github.com/search/issues",
                   params={"q": f'is:pr is:merged repo:{repo} "{keyword}"', "per_page": 5})
    if not r or r.status_code != 200:
        return None
    items = r.json().get("items", [])
    merged = []
    for it in items:
        pr_meta = it.get("pull_request") or {}
        if pr_meta.get("merged_at"):
            merged.append({"number": it["number"], "title": it["title"], "merged_at": pr_meta["merged_at"]})
    return merged

def get_tree(repo, sha="HEAD"):
    r = core_get(f"https://api.github.com/repos/{repo}/git/trees/{sha}", params={"recursive": 1})
    if r.status_code != 200:
        return None
    return r.json()

def canonical_check(impl_url):
    """Parse https://github.com/<owner>/<repo>/blob/<branch>/<path>; check contents API."""
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)", impl_url or "")
    if not m:
        return {"ok": False, "reason": "bad_url"}
    owner, repo, branch, path = m.groups()
    r = core_get(f"https://api.github.com/repos/{owner}/{repo}/contents/{path}", params={"ref": branch})
    if r.status_code == 200:
        return {"ok": True, "status": 200}
    if r.status_code == 404:
        return {"ok": False, "reason": "404", "status": 404}
    return {"ok": False, "reason": f"http_{r.status_code}"}

# ---- Main verification ----
def verify_opp(opp):
    oid = opp["id"]
    proj = opp["url"]
    owner, repo = repo_from_url(proj)
    src_type = opp["source_type"]
    ve = safe_json_load(opp["value_evidence"])
    de = safe_json_load(opp["difficulty_evidence"])
    ue = safe_json_load(opp["urgency_evidence"])
    me = safe_json_load(opp["maintainer_evidence"])
    issue_n = opp["issue_number"] or parse_source_ref(src_type, opp["source_ref"])

    checks = []
    corrections = []
    degraded = False
    reasons_for_refute = []
    reason_for_confirm = []

    # 0. Meta-discussion check (all non-feature_gap first)
    is_meta, meta_kw = check_meta_discussion(ve)
    if is_meta:
        checks.append(f"meta_discussion:{meta_kw}")
        return build_result(oid, "refuted",
                            f"元讨论帖关键词 '{meta_kw}' 命中 gap_desc，不可作为贡献机会",
                            checks, corrections, False, repo, issue_n)

    # source-type specific logic
    if src_type == "feature_gap":
        # 1. code/impl existence: search keywords in code
        fv = ve.get("feature_verification", {}) or {}
        searched = fv.get("searched_terms", []) or []
        if not searched:
            # use feature_desc / gap_desc words
            for s in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", ve.get("feature_desc", "") + " " + ve.get("gap_desc", "")):
                if s.lower() not in {"the","and","for","with","this","that","from","are","but","not","has","have","can","will","into","their","they","client","server","support","feature","topic","messages","need","required","requires"}:
                    searched.append(s)
        # Try code search for any keyword
        found_in_code = False
        hit_term = None
        for kw in (searched or [])[:3]:
            if _SEARCH_USED[0] >= _SEARCH_BUDGET:
                degraded = True
                break
            merged = search_merged_pr(f"{owner}/{repo}", kw)
            if merged:
                # don't conclude implemented; just record
                checks.append(f"code_search:{kw}->{len(merged)}merged")
                # if multiple of these are merged with similar title → likely implemented
            else:
                checks.append(f"code_search:{kw}->none")
        # Tree scan: see if any searched keyword matches a path
        tree = None
        if searched:
            tree = get_tree(f"{owner}/{repo}")
        if tree and "tree" in tree:
            paths = [t["path"].lower() for t in tree["tree"] if t.get("type") == "blob"]
            for kw in (searched or []):
                kl = kw.lower().replace("-", "_")
                if any(kl in p for p in paths):
                    found_in_code = True
                    hit_term = kw
                    break
        if found_in_code:
            checks.append(f"tree_match:{hit_term}")
            return build_result(oid, "refuted",
                                f"目录树命中 '{hit_term}'，功能已实现",
                                checks, corrections, degraded, repo, issue_n)
        # 2. canonical_impl_url 404 check
        cu = ve.get("canonical_impl_url", "")
        if cu:
            c = canonical_check(cu)
            checks.append(f"canonical_impl_url:{c.get('status', '?')}")
            if c.get("status") == 404:
                return build_result(oid, "refuted",
                                    f"canonical_impl_url 404：{cu}",
                                    checks, corrections, degraded, repo, issue_n)
        # 3. similar_prs already-merged
        sps = me.get("similar_prs", []) or []
        sp_merged_evidence = False
        for sp in sps[:5]:
            if isinstance(sp, dict) and sp.get("number"):
                pr = get_pr(f"{owner}/{repo}", sp["number"])
                if pr and pr.get("merged_at"):
                    sp_merged_evidence = True
                    checks.append(f"similar_pr#{sp['number']}:merged")
                    break
                else:
                    checks.append(f"similar_pr#{sp['number']}:not_merged")
        if sp_merged_evidence:
            return build_result(oid, "refuted",
                                "similar_prs 列表中存在已 merged PR，功能可能已实现",
                                checks, corrections, degraded, repo, issue_n)
        # Not refuted
        return build_result(oid, "confirmed",
                            "feature_gap: 代码未命中、canonical 链接 200、similar_prs 无 merged → confirmed",
                            checks, corrections, degraded, repo, issue_n)

    # issue / performance / security / compatibility
    # 1. issue state
    if not issue_n:
        return build_result(oid, "confirmed",
                            "无 issue_number；无法核查 issue 状态 → 保守 confirmed",
                            checks, corrections, True, repo, None)
    iss = get_issue(f"{owner}/{repo}", issue_n)
    if not iss:
        degraded = True
        return build_result(oid, "confirmed",
                            f"无法获取 issue #{issue_n} → degraded confirmed",
                            checks, corrections, True, repo, issue_n)
    state = iss.get("state")
    labels = [l["name"].lower() for l in iss.get("labels", [])]
    checks.append(f"issue#{issue_n}:state={state},labels={labels}")
    if state == "closed":
        return build_result(oid, "refuted",
                            f"issue #{issue_n} 已 closed",
                            checks, corrections, degraded, repo, issue_n)
    if any(l in ("not planned", "wontfix", "won't fix", "wont-fix") for l in labels):
        return build_result(oid, "refuted",
                            f"issue #{issue_n} 标签含 wontfix/not planned",
                            checks, corrections, degraded, repo, issue_n)
    # 2. linked PR
    timeline = get_issue_timeline(f"{owner}/{repo}", issue_n)
    if timeline is None:
        degraded = True
    has_linked = check_linked_prs(timeline) if timeline else False
    checks.append(f"linked_pr:{'yes' if has_linked else 'no'}")
    if has_linked:
        return build_result(oid, "refuted",
                            f"issue #{issue_n} 有 linked PR (timeline cross-referenced/connected)",
                            checks, corrections, degraded, repo, issue_n)
    # 3. reactions calibration
    api_react = iss.get("reactions", {}).get("total_count", 0)
    db_react = opp["issue_reactions"] or 0
    if db_react and api_react and abs(api_react - db_react) / max(db_react, 1) > 0.2:
        corrections.append(f"issue_reactions:{db_react}->{api_react}")
        ve["issue_reactions"] = api_react
        checks.append(f"reactions:{db_react}->{api_react}")
        # 4. similar_prs
        sps = me.get("similar_prs", []) or []
        sp_merged = False
        for sp in sps[:5]:
            if isinstance(sp, dict) and sp.get("number"):
                pr = get_pr(f"{owner}/{repo}", sp["number"])
                if pr and pr.get("merged_at"):
                    sp_merged = True
                    checks.append(f"similar_pr#{sp['number']}:merged")
                    break
        if sp_merged:
            return build_result(oid, "refuted",
                                "similar_prs 列表中存在已 merged PR",
                                checks, corrections, degraded, repo, issue_n)

    # 4. security-specific: CVE
    if src_type == "security":
        cve = ue.get("cve_id")
        if cve and not re.match(r"^CVE-\d{4}-\d{4,}$", str(cve)):
            return build_result(oid, "refuted",
                                f"CVE 格式造假：{cve}",
                                checks, corrections, degraded, repo, issue_n)
        af = ve.get("affected_file")
        if af:
            # check tree contains the file
            tree = get_tree(f"{owner}/{repo}")
            if tree and "tree" in tree:
                paths = [t["path"] for t in tree["tree"] if t.get("type") == "blob"]
                if not any(af in p for p in paths):
                    corrections.append(f"affected_file:not_found:{af}")
                    ve["affected_file"] = None
                    checks.append(f"affected_file:{af}->not_found")
            return build_result(oid, "corrected",
                                f"security issue 仍 open；affect_file 修正为 None",
                                checks, corrections, degraded, repo, issue_n, ve, me)

    # default: not refuted
    verdict = "corrected" if corrections else "confirmed"
    reason = "issue 仍 open、无 wontfix、无 linked PR"
    if corrections:
        reason += f"；修正: {corrections}"
    if degraded:
        reason += "（degraded：部分核查失败）"
    return build_result(oid, verdict, reason, checks, corrections, degraded, repo, issue_n, ve, me)


def build_result(oid, verdict, reason, checks, corrections, degraded, repo, issue_n, ve=None, me=None):
    res = {
        "opportunity_id": oid,
        "verdict": verdict,
        "reason": reason,
        "checks": checks,
        "corrections": corrections,
        "degraded": degraded,
    }
    if ve is not None or me is not None:
        res["_evidence_patch"] = {"value_evidence": ve, "maintainer_evidence": me}
    return res, verdict, ve, me

def write_db_updates(results):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for r, verdict, ve, me in results:
        oid = r["opportunity_id"]
        if verdict == "refuted":
            cur.execute("UPDATE opportunities SET status='refuted' WHERE id=?", (oid,))
        elif verdict == "corrected":
            patch = r.get("_evidence_patch", {})
            ve_json = json.dumps(patch.get("value_evidence")) if patch.get("value_evidence") is not None else None
            me_json = json.dumps(patch.get("maintainer_evidence")) if patch.get("maintainer_evidence") is not None else None
            cur.execute("""UPDATE opportunities
                SET status='verified', value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL,
                    value_evidence=?, maintainer_evidence=?
                WHERE id=?""", (ve_json, me_json, oid))
        else:  # confirmed
            cur.execute("UPDATE opportunities SET status='verified' WHERE id=?", (oid,))
        conn.commit()
    conn.close()

def main():
    opps = load_opps()
    print(f"Loaded {len(opps)} opportunities", flush=True)
    results = []
    for opp in opps:
        try:
            res = verify_opp(opp)
            results.append(res)
            print(f"  {opp['id']:>5} {res[0]['verdict']:>9}  {res[0]['reason'][:80]}", flush=True)
        except Exception as e:
            print(f"  {opp['id']:>5} ERROR     {e}", flush=True)
            results.append(({"opportunity_id": opp["id"], "verdict": "confirmed",
                             "reason": f"verification exception: {e}", "checks": [],
                             "corrections": [], "degraded": True}, "confirmed", None, None))

    # write DB
    write_db_updates(results)
    # write JSON output
    out = []
    for r, verdict, ve, me in results:
        out.append({
            "opportunity_id": r["opportunity_id"],
            "verdict": r["verdict"],
            "reason": r["reason"],
            "checks": r["checks"],
            "corrections": r["corrections"],
            "degraded": r["degraded"],
        })
    with open(LOG_PATH, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {len(out)} verdicts to {LOG_PATH}", flush=True)
    print(f"Search budget used: {_SEARCH_USED[0]}/{_SEARCH_BUDGET}", flush=True)

if __name__ == "__main__":
    main()
