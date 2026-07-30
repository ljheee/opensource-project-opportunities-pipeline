#!/usr/bin/env python3
"""Smoke tests for stages/scoring.py."""
import unittest

from stages import scoring


class TestExplicitDifficulty(unittest.TestCase):
    def test_hard_because(self):
        self.assertEqual(scoring._extract_explicit_difficulty("Hard because: concurrency"), "high")

    def test_medium_because(self):
        self.assertEqual(scoring._extract_explicit_difficulty("Medium because: some work"), "medium")

    def test_low_straightforward(self):
        self.assertEqual(scoring._extract_explicit_difficulty("Straightforward change"), "low")

    def test_negation(self):
        self.assertIsNone(scoring._extract_explicit_difficulty("not hard because"))

    def test_no_hint(self):
        self.assertIsNone(scoring._extract_explicit_difficulty(""))
        self.assertIsNone(scoring._extract_explicit_difficulty("some generic text"))


class TestScoreValue(unittest.TestCase):
    def test_issue_with_prod_signal_on_adopted_project(self):
        ve = {
            "canonical_impl_url": "",
            "issue_reactions": 1,
            "has_prod_signal": True,
        }
        self.assertEqual(scoring.score_value(ve, "unknown", "issue", project_adopted=True), "medium")

    def test_issue_without_prod_signal_stays_low(self):
        ve = {
            "canonical_impl_url": "",
            "issue_reactions": 1,
            "has_prod_signal": False,
        }
        self.assertEqual(scoring.score_value(ve, "unknown", "issue", project_adopted=True), "low")

    def test_security_with_prod_signal(self):
        ve = {
            "canonical_impl_url": "",
            "issue_reactions": 0,
            "has_prod_signal": True,
        }
        self.assertEqual(scoring.score_value(ve, "unknown", "security", project_adopted=True), "medium")

    def test_not_adopted_no_boost(self):
        ve = {
            "canonical_impl_url": "",
            "issue_reactions": 1,
            "has_prod_signal": True,
        }
        self.assertEqual(scoring.score_value(ve, "unknown", "issue", project_adopted=False), "low")


class TestScoreDifficulty(unittest.TestCase):
    def test_explicit_high_no_canonical(self):
        de = {
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": "Hard because: needs redesign",
        }
        self.assertEqual(scoring.score_difficulty(de), "high")

    def test_explicit_high_bumps_canonical_low_to_medium(self):
        de = {
            "canonical_impl_url": "https://github.com/foo/bar",
            "canonical_impl_loc": 50,
            "why_hard": "Hard because: complex algorithm",
        }
        self.assertEqual(scoring.score_difficulty(de), "medium")

    def test_explicit_medium_no_canonical(self):
        de = {
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": "Medium because: some work",
        }
        self.assertEqual(scoring.score_difficulty(de), "medium")

    def test_explicit_low_caps_high(self):
        de = {
            "canonical_impl_url": "https://github.com/foo/bar",
            "canonical_impl_loc": 1000,
            "why_hard": "Straightforward change",
        }
        # Large canonical LOC says high, but LLM explicitly says straightforward -> medium
        self.assertEqual(scoring.score_difficulty(de), "medium")


class TestWritebackStatus(unittest.TestCase):
    def test_rejected_becomes_obsolete(self):
        self.assertEqual(scoring._writeback_status("rejected", "verified"), "obsolete")
        self.assertEqual(scoring._writeback_status("rejected", "open"), "obsolete")

    def test_verified_preserved(self):
        self.assertEqual(scoring._writeback_status("welcoming", "verified"), "verified")
        self.assertEqual(scoring._writeback_status("unknown", "verified"), "verified")

    def test_open_preserved(self):
        self.assertEqual(scoring._writeback_status("welcoming", "open"), "open")


class TestRunPreservesVerified(unittest.TestCase):
    """复评集成测试：status='verified' + value=NULL 的行经 run() 后 status 仍为 verified。"""

    def _build_db(self, path):
        import sqlite3
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE projects (id TEXT PRIMARY KEY, stars INTEGER);
            CREATE TABLE project_meta (project_id TEXT, canonical_url TEXT);
            CREATE TABLE opportunities (
                id INTEGER PRIMARY KEY, project_id TEXT, task_id INTEGER,
                source_type TEXT, source_ref TEXT,
                value TEXT, difficulty TEXT, urgency TEXT, maintainer_signal TEXT,
                value_evidence TEXT, difficulty_evidence TEXT,
                urgency_evidence TEXT, maintainer_evidence TEXT,
                status TEXT DEFAULT 'open');
        """)
        conn.execute("INSERT INTO projects VALUES ('o/r', 1000)")
        conn.execute(
            "INSERT INTO opportunities (project_id, task_id, source_type, source_ref,"
            " value_evidence, difficulty_evidence, urgency_evidence, maintainer_evidence,"
            " status) VALUES ('o/r', 1, 'issue', 'issue:1', '{}', '{}', '{}', '{}', 'verified')")
        conn.commit()
        conn.close()

    def test_verified_row_scored_and_stays_verified(self):
        import os, sqlite3, tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "t.db")
            self._build_db(db)
            with mock.patch.object(scoring, "DB_PATH", db):
                scoring.run()
            row = sqlite3.connect(db).execute(
                "SELECT status, value FROM opportunities").fetchone()
            self.assertEqual(row[0], "verified")   # 不被冲回 open
            self.assertIsNotNone(row[1])           # 被复评选中并打分


if __name__ == "__main__":
    unittest.main()
