#!/usr/bin/env python3
"""Stage 4.8: 机器证据核账——用 GitHub API 验证 LLM 证据的真伪。

校验项与处置：
  source_ref issue 引用（双格式）  → 404/closed        → status='refuted'
  similar_prs[].number              → PR 不存在/merged 矛盾 → 剥离该条目
  welcome_labels                    → phantom label      → 剥离
  canonical_impl_url (/blob/)       → 404/仓库首页        → 置空（触发重算）
  feature_gap 无 feature_verification                    → status='refuted'
任何修改 → value=NULL 触发 scoring 复评。API 错误 → 跳过不误杀。
动作写 data/verify_log/YYYY-MM-DD.jsonl（source='validate'）。
"""
from __future__ import annotations

import argparse, json, os, re, sqlite3, sys, time
from datetime import datetime, timezone, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "pipeline.db")
DEFAULT_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "verify_log")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"
BASE_URL = "https://api.github.com"

_RETRY = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504],
               allowed_methods={"GET"}, raise_on_status=False)
_SESSION = requests.Session()
_SESSION.mount("https://", HTTPAdapter(max_retries=_RETRY))


def gh_get(path: str, params: dict | None = None):
    """返回 (status_code, json_or_none)。网络异常按 (None, None) 返回，由调用方按跳过处理。"""
    try:
        r = _SESSION.get(BASE_URL + path, headers=HEADERS, params=params, timeout=30)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, None
    except requests.RequestException:
        return None, None


# ── 纯解析/判定（可单测） ─────────────────────────────────────────────────────

_ISSUE_SHORT_RE = re.compile(r"issue:(\d+)$")
_ISSUE_URL_RE = re.compile(r"https://github\.com/([^/]+/[^/]+)/issues/(\d+)$")
_BLOB_RE = re.compile(r"https://github\.com/([^/]+/[^/]+)/blob/([^/]+)/(.+)$")


def parse_issue_ref(source_ref: str, project_id: str):
    """解析 issue 类 source_ref → (owner/repo, number)；非 issue 引用返回 None。
    兼容 'issue:NNN'（analyze.py 产出）与完整 URL（旧 analyze.md 链路）。"""
    if not source_ref:
        return None
    s = source_ref.strip()
    m = _ISSUE_SHORT_RE.fullmatch(s)
    if m:
        return project_id, int(m.group(1))
    m = _ISSUE_URL_RE.fullmatch(s)
    if m:
        return m.group(1), int(m.group(2))
    return None


def parse_blob_url(url: str):
    """解析 /blob/ 文件 URL → (owner/repo, branch, path)；非 blob URL 返回 None。"""
    if not url:
        return None
    m = _BLOB_RE.fullmatch(str(url).strip())
    if m:
        return m.group(1), m.group(2), m.group(3)
    return None


def _is_api_error(status) -> bool:
    """网络异常(None)或除 404 外的 4xx/5xx 都按 API 错误处理——未认证限流与
    secondary rate limit 常返回 403 而非 429，误当"证据不存在"会误杀证据。"""
    return status is None or (status >= 400 and status != 404)


def _loads(text):
    try:
        v = json.loads(text or "{}")
        return v if isinstance(v, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def validate_row(row: dict, gh, log) -> list:
    """对一行机会点执行核账，返回动作列表（不写库，写库由调用方按动作执行）。
    gh: gh_get 可调用对象；log: 接收日志 dict 的回调。"""
    actions = []
    oid = row["id"]
    evidence_changed = False

    # 1. source_ref issue 存续
    ref = parse_issue_ref(row.get("source_ref") or "", row["project_id"])
    issue_data = None
    if ref:
        repo, num = ref
        status, data = gh(f"/repos/{repo}/issues/{num}")
        if _is_api_error(status):
            return ["skip:api-error"]
        if status == 404:
            actions.append("refute:issue-404")
            log({"opportunity_id": oid, "project_id": row["project_id"], "source": "validate",
                 "verdict": "refuted", "reason": f"issue #{num} 不存在 (404)",
                 "checks": [f"issue:{repo}#{num}"], "corrections": []})
            return actions
        issue_data = data or {}
        if issue_data.get("state") == "closed":
            actions.append("refute:issue-closed")
            log({"opportunity_id": oid, "project_id": row["project_id"], "source": "validate",
                 "verdict": "refuted", "reason": f"issue #{num} 已关闭",
                 "checks": [f"issue:{repo}#{num}"], "corrections": []})
            return actions

    me = _loads(row.get("maintainer_evidence"))
    ve = _loads(row.get("value_evidence"))

    # 2. similar_prs 真伪
    prs = [p for p in me.get("similar_prs", []) if isinstance(p, dict)]
    kept = []
    for pr in prs:
        num = pr.get("number")
        if not isinstance(num, int):
            continue  # 无编号条目本来就无信号价值，直接丢弃不算动作
        status, data = gh(f"/repos/{row['project_id']}/pulls/{num}")
        if _is_api_error(status):
            kept.append(pr); continue  # API 错误：保留，不误杀
        if status == 404:
            evidence_changed = True
            continue  # 伪 PR 编号：剥离
        merged_api = bool((data or {}).get("merged_at"))
        if merged_api != bool(pr.get("merged")):
            evidence_changed = True
            continue  # merged 状态矛盾：剥离
        kept.append(pr)
    if evidence_changed and len(kept) != len(prs):
        me["similar_prs"] = kept
        actions.append("strip:similar_prs")

    # 3. welcome_labels 真伪（仅当能拿到 issue labels 时；feature_gap 行的 source_ref
    #    不是 issue 引用，issue_data=None，本项自然跳过——labels 校验依赖 issue 存在）
    labels_recorded = [l for l in me.get("welcome_labels", []) if isinstance(l, str)]
    if labels_recorded and issue_data is not None:
        actual = {l.get("name", "").lower() for l in issue_data.get("labels", []) if isinstance(l, dict)}
        kept_labels = [l for l in labels_recorded if l.lower() in actual]
        if len(kept_labels) != len(labels_recorded):
            me["welcome_labels"] = kept_labels
            actions.append("strip:welcome_labels")
            evidence_changed = True

    # 4. canonical_impl_url 有效性
    curl = str(ve.get("canonical_impl_url") or "").strip()
    if curl:
        blob = parse_blob_url(curl)
        if blob is None:
            # 非 /blob/ 文件 URL（仓库首页/目录页/其他）：按"无参考实现"置空
            ve["canonical_impl_url"] = ""
            actions.append("blank:canonical_impl_url")
            evidence_changed = True
        else:
            repo, branch, path = blob
            status, _ = gh(f"/repos/{repo}/contents/{path}", params={"ref": branch})
            if status == 404:
                ve["canonical_impl_url"] = ""
                actions.append("blank:canonical_impl_url")
                evidence_changed = True
            elif _is_api_error(status):
                pass  # API 错误：保留原值

    # 5. feature_gap 必须有核查证据（仅兜底 open 行；verified 行已由 verify 用全新
    #    证据独立做过存在性核查，豁免——否则 legacy 行会被 confirm 后再误 refute）
    if row.get("source_type") == "feature_gap" and row.get("status") == "open":
        fv = ve.get("feature_verification")
        ok = (isinstance(fv, dict)
              and isinstance(fv.get("searched_terms"), list) and fv["searched_terms"]
              and bool(fv.get("checked_at")))
        if not ok:
            actions.append("refute:no-feature-verification")
            log({"opportunity_id": oid, "project_id": row["project_id"], "source": "validate",
                 "verdict": "refuted", "reason": "feature_gap 缺失 feature_verification 核查证据",
                 "checks": ["feature_verification"], "corrections": []})
            return actions

    if evidence_changed:
        log({"opportunity_id": oid, "project_id": row["project_id"], "source": "validate",
             "verdict": "corrected", "reason": "剥离/置空伪证据: " + ",".join(actions),
             "checks": [], "corrections": actions})
        row["_new_maintainer_evidence"] = json.dumps(me, ensure_ascii=False)
        row["_new_value_evidence"] = json.dumps(ve, ensure_ascii=False)
    return actions


# ── 主流程 ──────────────────────────────────────────────────────────────────

def run(db_path=DEFAULT_DB, log_dir=DEFAULT_LOG_DIR, opp_ids=None, today=False,
        zombie_days=7, dry_run=False):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc)
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, now.strftime("%Y-%m-%d") + ".jsonl")

    def log(entry):
        entry["ts"] = now.isoformat()
        if not dry_run:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    try:
        conds, params = ["o.status IN ('open','verified')"], []
        scope_parts = []
        if opp_ids:
            scope_parts.append("o.id IN (%s)" % ",".join("?" * len(opp_ids)))
            params.extend(opp_ids)
        if today:
            scope_parts.append("DATE(o.last_seen_at) = DATE('now')")
        if scope_parts:
            # --opp-ids 与 --today 同时给时是并集：verify 参与者（可能很旧）∪ 今日新分析
            conds.append("(" + " OR ".join(scope_parts) + ")")
        rows = conn.execute(
            "SELECT o.id, o.project_id, o.source_type, o.source_ref, o.status,"
            " o.value_evidence, o.maintainer_evidence"
            " FROM opportunities o WHERE " + " AND ".join(conds), params).fetchall()
        print(f"待核账机会点：{len(rows)} 个")
        stats = {"refuted": 0, "corrected": 0, "skipped": 0, "clean": 0}
        for i, r in enumerate(rows):
            row = dict(r)
            actions = validate_row(row, gh_get, log)
            if "skip:api-error" in actions:
                stats["skipped"] += 1
                continue
            refuted = any(a.startswith("refute:") for a in actions)
            corrected = any(a.startswith(("strip:", "blank:")) for a in actions)
            if dry_run:
                if actions:
                    print(f"  [dry-run] id={row['id']}: {actions}")
            else:
                if refuted:
                    conn.execute("UPDATE opportunities SET status='refuted' WHERE id=?", (row["id"],))
                    stats["refuted"] += 1
                elif corrected:
                    conn.execute(
                        "UPDATE opportunities SET maintainer_evidence=?, value_evidence=?,"
                        " value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL"
                        " WHERE id=?",
                        (row.get("_new_maintainer_evidence", row["maintainer_evidence"]),
                         row.get("_new_value_evidence", row["value_evidence"]), row["id"]))
                    stats["corrected"] += 1
                else:
                    stats["clean"] += 1
            # 限速纪律：正式运行 1s（同 analyze.py）；dry-run 验证缩短为 0.2s 以免存量行卡数分钟
            time.sleep(0.2 if dry_run else 1)
            if (i + 1) % 50 == 0 and not dry_run:
                conn.commit()
        if not dry_run:
            conn.commit()

        # 僵尸行巡检：scoring JSON 解析失败遗留的 value=NULL open 行
        cutoff = (now - timedelta(days=zombie_days)).isoformat()
        zombies = conn.execute(
            "SELECT id, project_id, source_ref FROM opportunities"
            " WHERE status='open' AND value IS NULL AND last_seen_at < ?",
            (cutoff,)).fetchall()
        if zombies:
            print(f"WARN: {len(zombies)} 个僵尸 open 行（value IS NULL 超过 {zombie_days} 天），需人工排查：")
            for z in zombies[:20]:
                print(f"  id={z['id']} {z['project_id']} {z['source_ref']}")
        print(f"核账完成：{stats}")
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser(description="Machine-validate opportunity evidence via GitHub API")
    p.add_argument("--opp-ids", default="", help="逗号分隔；不给则按 --today 等条件选取")
    p.add_argument("--today", action="store_true", help="只核账 last_seen_at 为今天的行")
    p.add_argument("--zombie-days", type=int, default=7)
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--log-dir", default=DEFAULT_LOG_DIR)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    opp_ids = [int(x) for x in args.opp_ids.split(",") if x.strip()] or None
    run(db_path=args.db, log_dir=args.log_dir, opp_ids=opp_ids,
        today=args.today, zombie_days=args.zombie_days, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
