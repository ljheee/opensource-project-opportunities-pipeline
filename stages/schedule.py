#!/usr/bin/env python3
"""Stage 2: 调度决策，根据项目状态和变更情况生成今日 tasks。"""
import os, sqlite3, argparse
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipeline.db')

MAX_TASKS = {
    "triggered":     None,
    "incremental":   10,
    # bulk_first 数量由 CLI --batch-size 参数控制（run_bulk.sh 默认传 5），此处不设上限常量
    # （原 bulk_first=5 是死代码，gen_bulk_tasks 使用 args.batch_size 而非 MAX_TASKS['bulk_first']）
    "bulk_followup": 200,
}


def get_conn():
    return sqlite3.connect(DB_PATH)


def today():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def days_since(iso_str: str) -> int:
    if not iso_str:
        return 9999
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        # 若 LLM 写入无时区的 naive datetime，强制附加 UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except (ValueError, TypeError):
        return 9999  # 格式异常时保守地视为"很久没分析过"


def gen_triggered_tasks(conn, date, dry_run) -> int:
    """重大版本发布：active 项目 latest_release_at 有更新。"""
    cur = conn.execute("""
        SELECT p.id, p.latest_release, p.latest_release_at,
               MAX(t.finished_at) as last_analyzed
        FROM projects p
        LEFT JOIN tasks t ON t.project_id = p.id AND t.status = 'done'
        WHERE p.status = 'active'
          AND p.latest_release_at IS NOT NULL
          AND p.id NOT IN (
              SELECT project_id FROM tasks
              WHERE task_date = ? AND task_type = 'triggered'
          )
        GROUP BY p.id, p.latest_release, p.latest_release_at
    """, (date,))
    count = 0
    for row in cur.fetchall():
        pid, release, release_at, last_analyzed = row
        # 版本发布时间比上次分析时间新（统一转 datetime 对象再比较，避免 Z vs +00:00 格式差异）
        # last_analyzed 为 NULL 表示项目从未被分析过（首次进入 active）。
        # 首次分析交由 gen_incremental_tasks 以 first_active 触发，避免：
        #   1. task_type/trigger_reason 语义错误（triggered 应仅对应版本变更，非首次分析）
        #   2. triggered 无数量上限（MAX_TASKS["triggered"]=None），大批量新项目同时有
        #      latest_release_at 时可能在同一天生成过多任务
        if not last_analyzed:
            continue
        if release_at:
            try:
                dt_release = datetime.fromisoformat(release_at.replace('Z', '+00:00'))
                dt_analyzed = datetime.fromisoformat(last_analyzed.replace('Z', '+00:00'))
                # 统一为 aware datetime，避免 naive/aware 比较抛 TypeError
                if dt_release.tzinfo is None:
                    dt_release = dt_release.replace(tzinfo=timezone.utc)
                if dt_analyzed.tzinfo is None:
                    dt_analyzed = dt_analyzed.replace(tzinfo=timezone.utc)
                if dt_release <= dt_analyzed:
                    continue
            except (ValueError, TypeError):
                pass  # 格式异常时保守触发分析
        reason = f"new_release:{release or 'unknown'}"
        if dry_run:
            print(f"  [triggered] {pid} — {reason}")
            count += 1
        else:
            cur2 = conn.execute("""
                INSERT OR IGNORE INTO tasks (project_id, task_date, task_type, trigger_reason, status, created_at)
                VALUES (?, ?, 'triggered', ?, 'pending', ?)
            """, (pid, date, reason, datetime.now(timezone.utc).isoformat()))
            if cur2.rowcount > 0:
                count += 1
    return count


def _ts_after(a: str, b: str) -> bool:
    """Return True if timestamp a is strictly after b. Handles any UTC-offset format."""
    if not a or not b:
        return False
    try:
        dt_a = datetime.fromisoformat(a.replace('Z', '+00:00'))
        dt_b = datetime.fromisoformat(b.replace('Z', '+00:00'))
        if dt_a.tzinfo is None:
            dt_a = dt_a.replace(tzinfo=timezone.utc)
        if dt_b.tzinfo is None:
            dt_b = dt_b.replace(tzinfo=timezone.utc)
        return dt_a > dt_b
    except (ValueError, TypeError):
        return False


def gen_incremental_tasks(conn, date, dry_run) -> int:
    """对比 projects.prev_* 字段与当前值判断变化。"""
    cur = conn.execute("""
        SELECT p.id, p.stars, p.open_issues, p.last_commit_at,
               p.prev_stars, p.prev_open_issues,
               MAX(t.finished_at) as last_analyzed
        FROM projects p
        LEFT JOIN tasks t ON t.project_id = p.id AND t.status = 'done'
        WHERE p.status = 'active'
          AND p.id NOT IN (
              SELECT project_id FROM tasks
              WHERE task_date = ?
          )
        GROUP BY p.id, p.stars, p.open_issues, p.last_commit_at,
                 p.prev_stars, p.prev_open_issues
        ORDER BY last_analyzed ASC  -- NULLs sort first in SQLite ASC, prioritizing never-analyzed projects
    """, (date,))
    count = 0
    limit = MAX_TASKS['incremental']
    for row in cur.fetchall():
        if limit and count >= limit:
            break
        pid, stars, issues, commit_at, prev_stars, prev_issues, last_analyzed = row
        if days_since(last_analyzed) < 7:
            continue
        # prev_stars 为 NULL → 新项目首次进入 active，直接触发
        # last_analyzed 为 NULL 但 prev_stars 非 NULL → 数据不一致，保守触发
        if prev_stars is None or last_analyzed is None:
            reason = 'first_active'
        else:
            issues_delta   = abs((issues or 0) - (prev_issues or 0))
            stars_delta    = abs((stars  or 0) - (prev_stars  or 0))
            # issues/stars 为 None 表示本次抓取失败，不视为变化（避免 None→0 误判为大幅下降）
            # prev_issues 为 None 或 0: any new issue is a significant change (avoid ZeroDivisionError/TypeError)
            issues_changed = bool(issues is not None and issues_delta > 0 and (
                not prev_issues or issues_delta / prev_issues > 0.10))
            stars_changed  = bool(stars  and prev_stars  and stars_delta  / prev_stars  > 0.05)
            # commit_changed: 最后提交时间晚于上次分析时间（有新提交）
            # 使用 datetime 解析比较，正确处理非 UTC 时区偏移（如 +05:30）
            commit_changed = _ts_after(commit_at, last_analyzed)
            if not (issues_changed or stars_changed or commit_changed):
                continue
            issues_sign = "+" if (issues or 0) >= (prev_issues or 0) else "-"
            stars_sign  = "+" if (stars  or 0) >= (prev_stars  or 0) else "-"
            reason = (f"issues_delta:{issues_sign}{issues_delta}" if issues_changed else
                      f"stars_delta:{stars_sign}{stars_delta}"    if stars_changed  else "new_commit")
        if dry_run:
            print(f"  [incremental] {pid} — {reason}")
            count += 1
        else:
            cur2 = conn.execute("""
                INSERT OR IGNORE INTO tasks (project_id, task_date, task_type, trigger_reason, status, created_at)
                VALUES (?, ?, 'incremental', ?, 'pending', ?)
            """, (pid, date, reason, datetime.now(timezone.utc).isoformat()))
            if cur2.rowcount > 0:
                count += 1
    return count


def gen_bulk_tasks(conn, date, batch_size, dry_run) -> int:
    """Priority 3: A 类（anchor/ecosystem 来源）bulk_first 任务。"""
    cur = conn.execute("""
        SELECT p.id
        FROM projects p
        WHERE p.status = 'bulk_pending'
          AND p.source IN ('anchor', 'ecosystem')
          AND p.id NOT IN (
              SELECT project_id FROM tasks
              WHERE task_date = ? AND task_type = 'bulk_first'
          )
        ORDER BY p.stars DESC
        LIMIT ?
    """, (date, batch_size,))
    count = 0
    for row in cur.fetchall():
        pid = row[0]
        if dry_run:
            print(f"  [bulk_first] {pid}")
            count += 1
        else:
            cur2 = conn.execute("""
                INSERT OR IGNORE INTO tasks (project_id, task_date, task_type, trigger_reason, status, created_at)
                VALUES (?, ?, 'bulk_first', 'bulk_schedule', 'pending', ?)
            """, (pid, date, datetime.now(timezone.utc).isoformat()))
            if cur2.rowcount > 0:
                count += 1
    return count


def gen_bulk_followup_tasks(conn, date, batch_size, dry_run) -> int:
    """Priority 4: B 类（非 anchor/ecosystem）bulk_followup 任务，仅在无 bulk_first 时触发。"""
    # 只有今日还有未完成的 bulk_first 任务时才跳过 bulk_followup；
    # 若 bulk_first 任务全部 done/skipped，说明 A 类项目已处理完，可以开始 B 类
    existing = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE task_date=? AND task_type='bulk_first' AND status IN ('pending','running')", (date,)
    ).fetchone()[0]
    if existing > 0:
        return 0
    cur = conn.execute("""
        SELECT p.id
        FROM projects p
        WHERE p.status = 'bulk_pending'
          AND p.source NOT IN ('anchor', 'ecosystem')
          AND p.id NOT IN (
              SELECT project_id FROM tasks
              WHERE task_date = ? AND task_type = 'bulk_followup'
          )
        ORDER BY p.stars DESC
        LIMIT ?
    """, (date, batch_size,))
    count = 0
    for row in cur.fetchall():
        pid = row[0]
        if dry_run:
            print(f"  [bulk_followup] {pid}")
            count += 1
        else:
            cur2 = conn.execute("""
                INSERT OR IGNORE INTO tasks (project_id, task_date, task_type, trigger_reason, status, created_at)
                VALUES (?, ?, 'bulk_followup', 'bulk_schedule', 'pending', ?)
            """, (pid, date, datetime.now(timezone.utc).isoformat()))
            if cur2.rowcount > 0:
                count += 1
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['incremental', 'bulk_first'], default='incremental')
    parser.add_argument('--batch-size', type=int, default=5)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    conn = None
    date = today()
    total = 0

    try:
        conn = get_conn()
        if args.mode == 'incremental':
            n = gen_triggered_tasks(conn, date, args.dry_run)
            print(f"triggered:   {n}")
            total += n
            n = gen_incremental_tasks(conn, date, args.dry_run)
            print(f"incremental: {n}")
            total += n
        else:
            n = gen_bulk_tasks(conn, date, args.batch_size, args.dry_run)
            print(f"bulk_first:     {n}")
            total += n
            n = gen_bulk_followup_tasks(conn, date, MAX_TASKS['bulk_followup'], args.dry_run)
            print(f"bulk_followup:  {n}")
            total += n

        if not args.dry_run:
            conn.commit()
    finally:
        if conn is not None:
            conn.close()
    print(f"今日任务合计: {total}")


if __name__ == '__main__':
    main()
