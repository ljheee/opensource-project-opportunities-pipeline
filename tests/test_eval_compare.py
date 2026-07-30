#!/usr/bin/env python3
"""Smoke tests for stages/eval_compare.py."""
import json, os, sqlite3, tempfile, unittest

from stages import eval_compare as ec


class TestEvalCompare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.db = os.path.join(d, "t.db")
        self.golden = os.path.join(d, "golden.jsonl")
        self.baseline = os.path.join(d, "baseline.json")
        conn = sqlite3.connect(self.db)
        conn.execute("""CREATE TABLE opportunities (
            id INTEGER PRIMARY KEY, project_id TEXT, source_type TEXT, source_ref TEXT,
            status TEXT, value TEXT, last_seen_at TEXT,
            UNIQUE(project_id, source_type, source_ref))""")
        rows = [
            (1, "o/fake1", "feature_gap", "canonical:Java/license", "open", "high", "2026-07-01"),
            (2, "o/real1", "issue", "issue:42", "verified", "high", "2026-07-01"),
            (3, "o/real2", "issue", "issue:43", "refuted", "medium", "2026-07-01"),  # 误杀
            (4, "o/moved", "issue", "issue:44", "open", "high", "2026-07-29"),       # 窗口内被重分析
        ]
        conn.executemany("INSERT INTO opportunities VALUES (?,?,?,?,?,?,?)", rows)
        conn.commit(); conn.close()
        entries = [
            {"project": "o/fake1", "source_type": "feature_gap", "source_ref": "canonical:Java/license", "label": "fake"},
            {"project": "o/real1", "source_type": "issue", "source_ref": "issue:42", "label": "real"},
            {"project": "o/real2", "source_type": "issue", "source_ref": "issue:43", "label": "real"},
            {"project": "o/moved", "source_type": "issue", "source_ref": "issue:44", "label": "real"},
            {"project": "o/ghost", "source_type": "issue", "source_ref": "issue:99", "label": "real"},
        ]
        with open(self.golden, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_baseline_then_compare(self):
        ec.run_baseline(self.golden, self.db, self.baseline)
        # 模拟 v3 跑过：fake1 被 refuted，moved 被重分析（last_seen_at 变化）
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE opportunities SET status='refuted' WHERE id=1")
        conn.execute("UPDATE opportunities SET last_seen_at='2026-07-30' WHERE id=4")
        conn.commit(); conn.close()
        m = ec.run_compare(self.golden, self.db, self.baseline)
        self.assertEqual(m["fake_total"], 1)
        self.assertEqual(m["fake_killed"], 1)            # 假机会清除率 100%
        self.assertEqual(m["real_total"], 2)             # real1+real2（moved 剔除、ghost 缺失不计）
        self.assertEqual(m["real_killed"], 1)            # real2 被误杀 → 保留率 50%
        self.assertEqual(m["missing"], 1)                # ghost
        self.assertEqual(m["excluded_reanalyzed"], 1)    # moved
