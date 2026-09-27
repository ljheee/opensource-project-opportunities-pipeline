#!/usr/bin/env python3
"""Stage 4.7-ingest: 校验 verify LLM 裁决 JSON，落盘正式 JSONL 日志并审计。

verify_v3.md 会话把本批裁决写为单个 JSON 数组（.pending_<ts>.json 临时文件）；
本脚本在 CLI 退出后运行：schema 校验 → append 正式日志 → 审计。
坏条目隔离到 quarantine.jsonl；审计问题一律 WARN 不中断（机会点停留 open 可幂等续处理）。
"""
from __future__ import annotations

import argparse, json, os, re, sqlite3, sys
from datetime import datetime, timezone

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "pipeline.db")
DEFAULT_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "verify_log")

VERDICTS = ("confirmed", "refuted", "corrected")
VERDICT_TO_STATUS = {"confirmed": "verified", "refuted": "refuted", "corrected": "verified"}

# Controlled vocabulary for `checks`. verify_v3.md defines the checks procedurally, so
# the LLM had been inventing its own spellings: across 3605 historical occurrences there
# were 1352 distinct strings, 727 with no recognisable prefix. The same fact arrived as
# "issue_state:open" / "issue:open" / "issue:state=open" / "state:open", which makes the
# log impossible to aggregate programmatically. Keys below are exactly the checks the
# prompt actually specifies — nothing invented.
CHECK_VOCAB = (
    "meta_discussion",   # gap_desc keyword scan, no API needed
    "issue_state",       # state / state_reason
    "issue_labels",      # wontfix / not planned / question ...
    "linked_pr",         # timeline cross-referenced / connected
    "reactions_calibration",
    "similar_prs",       # merged implementation re-checked
    "code_search",       # feature_gap "does it already exist"
    "canonical_url",     # canonical_impl_url contents API
    "cve_format",
    "affected_file",
    "comments",
    "maintainer_response",
    "quote_verbatim",
    "repo_tree",
)

# Spellings seen in the historical logs that mean a canonical key above.
_CHECK_ALIASES = {
    "issue": "issue_state", "state": "issue_state", "issue_state": "issue_state",
    "get_issue": "issue_state", "issues": "issue_state",
    "label": "issue_labels", "labels": "issue_labels",
    "timeline": "linked_pr", "linked_pr": "linked_pr", "linked_prs": "linked_pr",
    "get_timeline": "linked_pr",
    "reactions": "reactions_calibration", "reactions_match": "reactions_calibration",
    "similar_pr": "similar_prs", "similar_prs": "similar_prs", "search": "similar_prs",
    "code_check": "code_search", "code_read": "code_search",
    "canonical_impl_url": "canonical_url", "contents": "canonical_url",
    "quote_check": "quote_verbatim", "quotes": "quote_verbatim",
    "maintainer": "maintainer_response", "maintainer_responses": "maintainer_response",
    "gap_desc": "meta_discussion",
    # Identity entries: a canonical key must resolve to itself, otherwise
    # "canonical_url:200" matches no alias, falls through to the joined-key pass and
    # loses its value ("canonical_url:pass"). "issue" stays singular-only so that
    # "issue_labels" is not swallowed by the state alias.
    "issue_state": "issue_state",
    "issue_label": "issue_labels", "issue_labels": "issue_labels",
    "linked_pr": "linked_pr",
    "reaction": "reactions_calibration",
    "code": "code_search", "codesearch": "code_search",
    "canonical": "canonical_url", "canonical_urls": "canonical_url",
    "pr_search": "similar_prs",
    "cve": "cve_format", "comment": "comments",
    "quote": "quote_verbatim",
    "affected_file": "affected_file", "repo_tree": "repo_tree",
    "meta": "meta_discussion",
    "reactions_calibration": "reactions_calibration",
    "code_search": "code_search",
    "canonical_url": "canonical_url",
    "cve_format": "cve_format",
    "comments": "comments",
    "quote_verbatim": "quote_verbatim",
    "maintainer_response": "maintainer_response",
    "meta_discussion": "meta_discussion",
}

# Values that mean "this check found nothing", normalised across phrasings.
_NONE_VALUES = {
    "none", "[]", "no", "null", "无", "无cross-referenced", "无linked-pr",
    "无cross-referenced pr", "no cross-referenced pr", "no linked pr",
    "no cross-referenced", "no linked-pr", "无linked pr",
}
_OPEN_VALUES = {"open", "state=open", "是"}


# Whole sentences of the form "GET /repos/o/r/issues/869 state=open" — a real
# historical habit, and unambiguously an issue_state check.
_API_SENTENCE = re.compile(r"issues?/(\d+)\D+state\s*[=:]\s*(\w+)", re.I)
# "issue#1247" / "issue 1247" — an issue reference whose verdict is stated elsewhere.
_ISSUE_REF = re.compile(r"^issue\s*#?\s*(\d+)\b", re.I)
# Underscore/space-joined negations: timeline_no_linked_pr, no wontfix label, ...
_NEGATED = re.compile(r"^no[_\s]+|_no[_\s]+", re.I)


# Trailing tokens that are really the *value* of a joined key: issue_state_open.
_VALUE_TOKENS = {
    "open", "closed", "completed", "not_planned", "notplanned", "reopened",
    "hit", "miss", "present", "absent", "none", "ok", "fail", "failed", "200", "404",
}
# Words that identify a check by content rather than by key: "no wontfix label".
_CONTENT_KEY = [
    (r"wontfix|not[- _]planned|label|标签", "issue_labels"),
    (r"linked|cross[- _]?ref|xref|timeline", "linked_pr"),
    (r"meta|gap_desc|元讨论", "meta_discussion"),
    (r"reaction|\+1", "reactions_calibration"),
    (r"code|grep|search_code|tree|dir", "code_search"),
    (r"merged_pr|similar_pr", "similar_prs"),
    (r"cve", "cve_format"),
    (r"maintainer|owner|member|collaborator", "maintainer_response"),
    (r"quote|verbatim", "quote_verbatim"),
    (r"canonical", "canonical_url"),
    (r"comment", "comments"),
    (r"affected_file", "affected_file"),
]


def _normalise_joined(text: str) -> str | None:
    """Handle forms the colon-based pass can't see: fully joined keys and API sentences.

    Returns a canonical string, or None when the input is genuinely free-form detail
    that only belongs in `reason`.
    """
    low = text.lower()

    m = _API_SENTENCE.search(text)
    if m:
        return f"issue_state:{m.group(2).lower()}"

    m = _ISSUE_REF.match(text)
    if m:
        rest = text[m.end():].strip()
        st = re.search(r"state\s*[=:]\s*(\w+)", rest, re.I)
        return f"issue_state:{st.group(1).lower()}" if st else text

    if re.match(r"^labels?\s*[=：]", low):
        return f"issue_labels:{text.split('=', 1)[1].split('=', 1)[-1].strip()}"

    # "issue_state_open" -> key "issue_state", value "open"
    parts = [p for p in re.split(r"[_\s]+", low) if p]
    for cut in range(len(parts) - 1, 0, -1):
        head, rest = "_".join(parts[:cut]), "_".join(parts[cut:])
        if rest in _VALUE_TOKENS:
            key = _CHECK_ALIASES.get(head)
            if key:
                return f"{key}:{rest}"

    # Strip a leading negation, then resolve the key — "no_linked_pr" -> linked_pr:none
    stripped = re.sub(r"^no[_\s-]+", "", low)
    key = _CHECK_ALIASES.get(stripped) or _CHECK_ALIASES.get(stripped.rstrip("_s"))
    if key is None:
        first = re.split(r"[_\s=/]", stripped)[0]
        key = _CHECK_ALIASES.get(first)
    if key is None:
        for pattern, k in _CONTENT_KEY:
            if re.search(pattern, low):
                key = k
                break
    if key is None:
        return None

    negated = bool(_NEGATED.search(low)) or low.startswith("no")
    value = "none" if negated else "pass"
    if "=" in text or "match" in low or "consistent" in low or "一致" in text:
        value = "pass"
    return f"{key}:{value}"


def normalise_check(raw) -> str:
    """Fold a free-form check string into `<canonical_key>:<value>`.

    Unknown keys are preserved verbatim rather than dropped: an unrecognised check is
    still real evidence, and silently discarding it would lose information. Aggregation
    can filter on the known vocabulary later.
    """
    if not isinstance(raw, str):
        raw = str(raw)
    text = raw.strip()
    if not text:
        return ""
    head, sep, tail = text.partition(":")
    if not sep:
        head, tail = text, "pass"
    key = _CHECK_ALIASES.get(head.strip().lower().rstrip(":：").strip())
    if key is None:
        joined = _normalise_joined(text)
        if joined is not None:
            return joined
        return text
    value = tail.strip().rstrip(";").strip()
    if not value:
        value = "pass"
    return f"{key}:{_normalise_value(key, value)}"


# Values meaning "the thing I looked for is absent", across every phrasing seen.
_NONE_WORDS = {
    "none", "no", "false", "absent", "miss", "missing", "[]", "{}", "null", "0",
    "no_linked_pr", "no-linked-pr", "no_linked", "0_xref", "0_cross_ref_pr",
    "no_xref", "no cross-referenced pr", "no linked pr", "clean", "0_events",
    "not_found", "notfound", "未找到", "无",
}
# Values meaning "found".
_PRESENT_WORDS = {
    "present", "yes", "true", "found", "hit", "1", "有", "存在", "有找到",
}


def _normalise_value(key: str, value: str) -> str:
    """Canonicalise a check's value.

    Only the absent/present axis is collapsed — those are what get counted across the
    whole log. Domain values stay verbatim, because `issue_state:completed`,
    `issue_labels:question` and `canonical_url:404` are the actual signal and must not
    be flattened into each other.
    """
    v = value.strip()
    low = v.lower()
    flat = low.replace(" ", "_").replace("-", "_")
    if low in _NONE_WORDS or flat in _NONE_WORDS:
        return "none"
    if low in _PRESENT_WORDS or flat in _PRESENT_WORDS:
        return "present"
    if key == "issue_state":
        m = re.search(r"(open|closed|completed|not[_ ]?planned|reopened|duplicate)",
                      v, re.I)
        if m:
            return m.group(1).lower().replace(" ", "_")
    # CJK and mixed phrasings carry no separator ("无linked-PR", "无cross-referenced"),
    # so exact-set lookup misses them — match on the negation/presence marker instead.
    if re.search(r"^\s*(无|未找到|没有|not[\s_-]*found|does not have)\b|^\s*无", v, re.I) \
       or re.match(r"^no[\s_-]|^none$|^无", low):
        return "none"
    if re.match(r"^有|^(present|yes|true|found)\b", v, re.I):
        return "present"
    return v


def normalise_correction(raw) -> str:
    """Corrections arrive as bare strings ("blank:canonical_impl_url") or as
    {"field": ..., "new": ...} dicts. Reduce both to a single stable string form."""
    if isinstance(raw, dict):
        field = raw.get("field") or raw.get("column") or raw.get("name") or ""
        new = raw.get("new") or raw.get("value") or ""
        return f"{field} -> {new}".strip() if field else str(raw)
    if not isinstance(raw, str):
        raw = str(raw)
    return raw.strip()


def validate_entry(e) -> str | None:
    """返回 None 表示合法，否则返回错误描述。"""
    if not isinstance(e, dict):
        return "条目不是 JSON 对象"
    if not isinstance(e.get("opportunity_id"), int) or isinstance(e.get("opportunity_id"), bool):
        return f"opportunity_id 缺失或非 int: {e.get('opportunity_id')!r}"
    if e.get("verdict") not in VERDICTS:
        return f"verdict 非法: {e.get('verdict')!r}"
    if not isinstance(e.get("reason"), str) or not e["reason"].strip():
        return "reason 缺失或为空"
    return None


def _append_jsonl(path: str, obj: dict):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def ingest(pending_path, opp_ids, db_path=DEFAULT_DB, log_dir=DEFAULT_LOG_DIR, dry_run=False) -> int:
    """校验并落盘一批裁决，返回进程退出码（0=正常或仅 WARN，1=用法错误）。"""
    now = datetime.now(timezone.utc)
    log_path = os.path.join(log_dir, now.strftime("%Y-%m-%d") + ".jsonl")
    quarantine_path = os.path.join(log_dir, "quarantine.jsonl")

    if not os.path.exists(pending_path):
        print(f"WARN: pending 文件不存在（verify CLI 可能失败）: {pending_path}")
        return 0
    try:
        with open(pending_path, encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARN: pending 文件解析失败: {pending_path}: {e}")
        if not dry_run:
            os.makedirs(log_dir, exist_ok=True)
            _append_jsonl(quarantine_path, {"_error": str(e), "_file": pending_path,
                                            "ts": now.isoformat()})
        return 0
    if not isinstance(entries, list):
        print(f"WARN: pending 文件不是 JSON 数组: {pending_path}")
        return 0

    valid, bad = [], []
    for e in entries:
        err = validate_entry(e)
        (bad if err else valid).append((e, err) if err else e)

    # 审计 1：漏判（裁决数少于本批机会点数）
    judged_ids = {e["opportunity_id"] for e in valid}
    missing = [i for i in opp_ids if i not in judged_ids]
    if missing:
        print(f"WARN: {len(missing)} 条机会点无裁决（停留 open 下次续处理）: {missing[:10]}")
    # 审计 2：裁决了不在本批的 id
    extra = [i for i in judged_ids if i not in set(opp_ids)]
    if extra:
        print(f"WARN: 裁决了 OPP_ID_LIST 之外的 id: {extra[:10]}")

    if dry_run:
        print(f"[dry-run] 合法 {len(valid)} 条，隔离 {len(bad)} 条，审计完成，未落盘")
        return 0

    os.makedirs(log_dir, exist_ok=True)
    for e in valid:
        e["checks"] = [n for n in (normalise_check(c) for c in (e.get("checks") or [])) if n]
        e["corrections"] = [n for n in (normalise_correction(c)
                                         for c in (e.get("corrections") or [])) if n]
        e["source"] = "verify"
        e["ts"] = now.isoformat()
        _append_jsonl(log_path, e)
    for e, err in bad:
        _append_jsonl(quarantine_path, {"_error": err, "entry": e, "ts": now.isoformat()})

    # 审计 3：DB 行数（违规 DELETE）与状态一致性抽查
    if opp_ids:
        conn = sqlite3.connect(db_path)
        try:
            marks = ",".join("?" * len(opp_ids))
            rows = dict(conn.execute(
                f"SELECT id, status FROM opportunities WHERE id IN ({marks})",
                list(opp_ids)).fetchall())
        finally:
            conn.close()
        deleted = [i for i in opp_ids if i not in rows]
        if deleted:
            print(f"WARN: {len(deleted)} 行在 DB 中不存在（verify 违规 DELETE？）: {deleted[:10]}")
        for e in valid:
            expect = VERDICT_TO_STATUS[e["verdict"]]
            actual = rows.get(e["opportunity_id"])
            if actual is not None and actual != expect:
                print(f"WARN: id={e['opportunity_id']} verdict={e['verdict']} 但 DB status='{actual}'（期望 '{expect}'）")

    # 清理已处理的 pending 文件
    try:
        os.remove(pending_path)
    except OSError:
        pass
    print(f"ingest 完成：落盘 {len(valid)} 条，隔离 {len(bad)} 条")
    return 0


def main():
    p = argparse.ArgumentParser(description="Ingest verify verdicts into JSONL log with audit")
    p.add_argument("pending_file")
    p.add_argument("--opp-ids", default="", help="逗号分隔的本批机会点 ID")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--log-dir", default=DEFAULT_LOG_DIR)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    opp_ids = [int(x) for x in args.opp_ids.split(",") if x.strip()]
    sys.exit(ingest(args.pending_file, opp_ids, db_path=args.db,
                    log_dir=args.log_dir, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
