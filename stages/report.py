#!/usr/bin/env python3
"""Stage 5: 读取 SQLite，生成当日 Markdown 摘要报告。"""
import os, sqlite3, argparse
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipeline.db')
REPORTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'reports')


def get_conn():
    return sqlite3.connect(DB_PATH)


def _title_cell(o) -> str:
    """Markdown table cell for an opportunity title.

    Escapes the characters that would break a table cell, and turns the title into
    a link when source_ref is a full GitHub issue URL (issue/performance/security/
    compatibility rows store the URL, other rows store `issue:<n>`).
    """
    title_text = (o['title'] or '').replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]').replace('|', '\\|').replace('\n', ' ').replace('\r', '')
    source_ref = o['source_ref'] or ''
    if source_ref.startswith('https://'):
        return f"[{title_text}]({source_ref})"
    return title_text


def render_report(date: str) -> str:
    conn = None
    try:
        conn = get_conn()
        conn.row_factory = sqlite3.Row

        # 今日完成的任务
        tasks = conn.execute("""
            SELECT t.id, t.project_id, t.task_type, t.trigger_reason,
                   p.stars, p.language, p.url,
                   m.canonical_name, m.canonical_lang
            FROM tasks t
            JOIN projects p ON p.id = t.project_id
            LEFT JOIN project_meta m ON m.project_id = t.project_id
            WHERE t.task_date = ? AND t.status = 'done'
            ORDER BY p.stars DESC
        """, (date,)).fetchall()

        # 今日分析过的项目的高价值机会（通过 project_id 关联今日完成的任务）
        opps = conn.execute("""
            SELECT o.*, p.url as project_url, p.language
            FROM opportunities o
            JOIN projects p ON p.id = o.project_id
            WHERE o.project_id IN (
                SELECT DISTINCT project_id FROM tasks
                WHERE task_date = ? AND status = 'done'
            )
              AND o.value IN ('high', 'medium')
              AND o.difficulty IS NOT NULL
              AND o.urgency IS NOT NULL
              AND o.status IN ('open', 'verified')
            ORDER BY
              CASE o.value WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
              CASE o.urgency WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
              CASE o.difficulty WHEN 'low' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END
        """, (date,)).fetchall()

        # 已通过对抗验证、但规则评分给了 low 的行。
        # 这是「验证说好、规则说不值」的矛盾状态：上游表按 value IN ('high','medium') 过滤，
        # 这类行会被整类漏掉。2026-10-20 实测全库有 22 条（占已验证行的 2.6%），全是
        # 「无 canonical 参照 + reactions<5」被判 low 的行——它们不是陈旧评分，是规则与
        # 语义层真的冲突，列出来供人工判断。
        verified_low = conn.execute("""
            SELECT o.*, p.url as project_url, p.language
            FROM opportunities o
            JOIN projects p ON p.id = o.project_id
            WHERE o.project_id IN (
                SELECT DISTINCT project_id FROM tasks
                WHERE task_date = ? AND status = 'done'
            )
              AND o.value = 'low'
              AND o.difficulty IS NOT NULL
              AND o.urgency IS NOT NULL
              AND o.status = 'verified'
            ORDER BY
              CASE o.urgency WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
              CASE o.difficulty WHEN 'low' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END
        """, (date,)).fetchall()

        # 全局统计
        stats = conn.execute("""
            SELECT
              (SELECT COUNT(*) FROM projects WHERE status IN ('active', 'analyzing'))           as active_total,
              (SELECT COUNT(*) FROM projects WHERE status IN ('bulk_pending', 'discovered'))    as pending,
              (SELECT COUNT(*) FROM opportunities WHERE status IN ('open', 'verified'))         as open_opps,
              (SELECT COUNT(*) FROM opportunities WHERE status = 'verified')                    as verified_opps,
              (SELECT COUNT(*) FROM opportunities
               WHERE DATE(first_seen_at) = ? AND status IN ('open', 'verified'))                as new_opps_today
        """, (date,)).fetchone()
    finally:
        if conn is not None:
            conn.close()

    lines = [
        f"# GitHub 开源机会分析报告 — {date}",
        "",
        "## 全局概览",
        "",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 监控中项目 | {stats['active_total']} |",
        f"| 存量待分析 | {stats['pending']} |",
        f"| 开放机会点 | {stats['open_opps']} |",
        f"| 已验证机会点 | {stats['verified_opps']} |",
        f"| 今日新增   | {stats['new_opps_today']} 个机会点 |",
        f"| 今日分析   | {len(tasks)} 个项目 |",
        "",
        "---",
        "",
        "## 今日分析项目",
        "",
    ]

    for t in tasks:
        canonical = f"{t['canonical_name']} ({t['canonical_lang']})" if t['canonical_name'] else "—"
        lines += [
            f"### [{t['project_id']}]({t['url']}) ⭐{t['stars']}",
            f"- **语言**: {t['language']}  **原版**: {canonical}",
            f"- **触发**: `{t['task_type']}` — {t['trigger_reason'] or '—'}",
            "",
        ]

    lines += [
        "---",
        "",
        "## 高价值贡献机会",
        "",
        "> 展示今日分析项目当前所有 open/verified 高价值机会（含历史轮次发现、今日仍 open 的机会点）。",
        "",
        "| 项目 | 标题 | 类型 | 价值 | 难度 | 紧迫 | 信号 | 验证 |",
        "|------|------|------|------|------|------|------|------|",
    ]

    for o in opps:
        signal = o['maintainer_signal'] or '—'
        verified_mark = '✓' if o['status'] == 'verified' else ''
        lines.append(
            f"| [{o['project_id']}]({o['project_url']}) "
            f"| {_title_cell(o)} "
            f"| `{o['source_type']}` "
            f"| {o['value']} "
            f"| {o['difficulty']} "
            f"| {o['urgency']} "
            f"| {signal} "
            f"| {verified_mark} |"
        )

    if verified_low:
        lines += [
            "",
            "---",
            "",
            "## 已验证但评级偏低的补充机会",
            "",
            "> 这些机会点**已通过对抗性验证**（`status=verified`），规则评分却给了 `low`。"
            "「验证说好、规则说不值」是矛盾状态——上面那张表按价值过滤，会把它们整类漏掉，"
            "所以单列在这里供人工判断。",
            "",
            "| 项目 | 标题 | 类型 | 价值 | 难度 | 紧迫 | 信号 |",
            "|------|------|------|------|------|------|------|",
        ]
        for o in verified_low:
            lines.append(
                f"| [{o['project_id']}]({o['project_url']}) "
                f"| {_title_cell(o)} "
                f"| `{o['source_type']}` "
                f"| {o['value']} "
                f"| {o['difficulty']} "
                f"| {o['urgency']} "
                f"| {o['maintainer_signal'] or '—'} |"
            )

    lines += ["", "---", "", f"*生成时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=datetime.now(timezone.utc).strftime('%Y-%m-%d'))
    args = parser.parse_args()

    os.makedirs(REPORTS_DIR, exist_ok=True)
    content = render_report(args.date)
    out_path = os.path.join(REPORTS_DIR, f"{args.date}.md")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"报告已生成: {out_path}")


if __name__ == '__main__':
    main()
