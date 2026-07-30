#!/usr/bin/env python3
"""评测集对比：golden.jsonl vs opportunities 表，量化 v3 相对 v2 的精度。

--baseline：快照 golden 命中行的当前状态（v3 开启前执行一次）
--compare ：对比 baseline 与当前状态，输出假机会清除率/真机会保留率/逐条 diff
窗口内被重分析（last_seen_at 变化）的行从指标剔除，单独列"需人工复核"。
退出码：0 正常；2 真机会保留率 < 95%（红线）；1 用法/数据错误。
"""
from __future__ import annotations

import argparse, json, os, sqlite3, sys
from datetime import datetime, timezone

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "pipeline.db")
DEFAULT_GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "eval", "golden.jsonl")
DEFAULT_BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "eval", "baseline_v2.json")

RETENTION_REDLINE = 0.95


def load_golden(path):
    entries = []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            for k in ("project", "source_type", "source_ref", "label"):
                if k not in e:
                    raise ValueError(f"golden 第 {ln} 行缺字段 {k}")
            if e["label"] not in ("real", "fake"):
                raise ValueError(f"golden 第 {ln} 行 label 非法: {e['label']}")
            entries.append(e)
    return entries


def _key(e):
    return (e["project"], e["source_type"], e["source_ref"])


def _fetch(db_path, keys):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        out = {}
        for project, source_type, source_ref in keys:
            row = conn.execute(
                "SELECT id, status, value, last_seen_at FROM opportunities"
                " WHERE project_id=? AND source_type=? AND source_ref=?",
                (project, source_type, source_ref)).fetchone()
            out[(project, source_type, source_ref)] = dict(row) if row else None
        return out
    finally:
        conn.close()


def run_baseline(golden_path, db_path, out_path):
    entries = load_golden(golden_path)
    rows = _fetch(db_path, [_key(e) for e in entries])
    snap = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "rows": {"|".join(k): v for k, v in rows.items()},
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    found = sum(1 for v in rows.values() if v)
    print(f"baseline 已快照：{found}/{len(entries)} 条 golden 命中 → {out_path}")


def run_compare(golden_path, db_path, baseline_path) -> dict:
    entries = load_golden(golden_path)
    with open(baseline_path, encoding="utf-8") as f:
        base = json.load(f)["rows"]
    current = _fetch(db_path, [_key(e) for e in entries])

    m = {"fake_total": 0, "fake_killed": 0, "real_total": 0, "real_killed": 0,
         "missing": 0, "excluded_reanalyzed": 0}
    false_kills, surviving_fakes, review = [], [], []
    for e in entries:
        k = _key(e)
        cur = current.get(k)
        b = base.get("|".join(k))
        if cur is None:
            m["missing"] += 1
            review.append(f"MISSING  {'|'.join(k)}")
            continue
        if b and b.get("last_seen_at") != cur.get("last_seen_at"):
            m["excluded_reanalyzed"] += 1
            review.append(f"REANALYZED {'|'.join(k)} (baseline {b.get('last_seen_at')} → {cur.get('last_seen_at')})")
            continue
        killed = cur["status"] == "refuted"
        if e["label"] == "fake":
            m["fake_total"] += 1
            if killed:
                m["fake_killed"] += 1
            else:
                surviving_fakes.append(f"SURVIVED-FAKE {'|'.join(k)} status={cur['status']}")
        else:
            m["real_total"] += 1
            if killed:
                m["real_killed"] += 1
                false_kills.append(f"FALSE-KILL {'|'.join(k)} notes={e.get('notes','')}")

    fake_rate = m["fake_killed"] / m["fake_total"] if m["fake_total"] else None
    retention = (1 - m["real_killed"] / m["real_total"]) if m["real_total"] else None
    print("=" * 60)
    print(f"假机会清除率 : {m['fake_killed']}/{m['fake_total']}"
          + (f" = {fake_rate:.0%}" if fake_rate is not None else " (无 fake 样本)"))
    print(f"真机会保留率 : {m['real_total'] - m['real_killed']}/{m['real_total']}"
          + (f" = {retention:.0%}（红线 ≥95%）" if retention is not None else " (无 real 样本)"))
    print(f"缺失 {m['missing']}，窗口内重分析剔除 {m['excluded_reanalyzed']}")
    for title, items in (("【误杀（必须人工复核）】", false_kills),
                         ("【存活的假机会】", surviving_fakes),
                         ("【需人工复核】", review)):
        if items:
            print(title)
            for it in items:
                print("  " + it)
    m["retention"] = retention
    return m


def main():
    p = argparse.ArgumentParser(description="Compare golden eval set against opportunities table")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--baseline", action="store_true")
    g.add_argument("--compare", action="store_true")
    p.add_argument("--golden", default=DEFAULT_GOLDEN)
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--baseline-file", default=DEFAULT_BASELINE)
    args = p.parse_args()
    if args.baseline:
        run_baseline(args.golden, args.db, args.baseline_file)
        sys.exit(0)
    m = run_compare(args.golden, args.db, args.baseline_file)
    if m["retention"] is not None and m["retention"] < RETENTION_REDLINE:
        print("ERROR: 真机会保留率低于红线 95%，verify 存在误杀，禁止进入存量回扫。")
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
