#!/usr/bin/env python3
"""Stage 4.7-ingest: 校验 verify LLM 裁决 JSON，落盘正式 JSONL 日志并审计。

verify_v3.md 会话把本批裁决写为单个 JSON 数组（.pending_<ts>.json 临时文件）；
本脚本在 CLI 退出后运行：schema 校验 → append 正式日志 → 审计。
坏条目隔离到 quarantine.jsonl；审计问题一律 WARN 不中断（机会点停留 open 可幂等续处理）。
"""
from __future__ import annotations

import argparse, json, os, sqlite3, sys
from datetime import datetime, timezone

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "pipeline.db")
DEFAULT_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "verify_log")

VERDICTS = ("confirmed", "refuted", "corrected")
VERDICT_TO_STATUS = {"confirmed": "verified", "refuted": "refuted", "corrected": "verified"}


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
        e.setdefault("checks", [])
        e.setdefault("corrections", [])
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
