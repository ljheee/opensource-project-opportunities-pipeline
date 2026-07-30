#!/usr/bin/env python3
"""Smoke tests for stages/report.py render_report()."""
import os, sqlite3, tempfile, unittest
from unittest import mock

from stages import report


class TestReportStatusFilter(unittest.TestCase):
    def _build_db(self, path):
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE projects (id TEXT PRIMARY KEY, url TEXT, stars INTEGER,
                                   language TEXT, status TEXT, latest_release TEXT);
            CREATE TABLE project_meta (project_id TEXT, canonical_name TEXT,
                                       canonical_lang TEXT, canonical_url TEXT);
            CREATE TABLE tasks (id INTEGER PRIMARY KEY, project_id TEXT, task_date TEXT,
                                task_type TEXT, trigger_reason TEXT, status TEXT);
            CREATE TABLE opportunities (
                id INTEGER PRIMARY KEY, project_id TEXT, task_id INTEGER,
                source_type TEXT, source_ref TEXT, title TEXT,
                value TEXT, difficulty TEXT, urgency TEXT, maintainer_signal TEXT,
                status TEXT DEFAULT 'open', first_seen_at TEXT, last_seen_at TEXT);
        """)
        conn.execute("INSERT INTO projects VALUES ('o/r','https://github.com/o/r',100,'Go','active','v1')")
        conn.execute("INSERT INTO tasks VALUES (1,'o/r','2026-07-30','triggered','x','done')")
        base = "INSERT INTO opportunities (project_id, task_id, source_type, source_ref, title," \
               " value, difficulty, urgency, status, first_seen_at) VALUES" \
               " ('o/r',1,'issue','issue:1',?,'high','low','high',?,'2026-07-30T01:00:00+00:00')"
        conn.execute(base, ("verified opp", "verified"))
        conn.execute(base, ("open opp", "open"))
        conn.execute(base, ("refuted opp", "refuted"))
        conn.execute(base, ("draft opp", "draft"))
        conn.commit()
        conn.close()

    def test_verified_shown_refuted_and_draft_hidden(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "t.db")
            self._build_db(db)
            with mock.patch.object(report, "DB_PATH", db):
                content = report.render_report("2026-07-30")
        self.assertIn("verified opp", content)
        self.assertIn("open opp", content)
        self.assertNotIn("refuted opp", content)
        self.assertNotIn("draft opp", content)
        # 统计口径：open+verified=2，refuted/draft 不计
        self.assertIn("| 开放机会点 | 2 |", content)
        self.assertIn("| 今日新增   | 2 个机会点 |", content)
        self.assertIn("| 已验证机会点 | 1 |", content)
