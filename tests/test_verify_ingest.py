#!/usr/bin/env python3
"""Smoke tests for stages/verify_ingest.py."""
import json, os, sqlite3, tempfile, unittest

from stages import verify_ingest as vi


class TestValidateEntry(unittest.TestCase):
    def test_valid(self):
        self.assertIsNone(vi.validate_entry(
            {"opportunity_id": 1, "verdict": "confirmed", "reason": "ok"}))

    def test_bad_verdict(self):
        self.assertIsNotNone(vi.validate_entry(
            {"opportunity_id": 1, "verdict": "sure", "reason": "x"}))

    def test_missing_reason(self):
        self.assertIsNotNone(vi.validate_entry(
            {"opportunity_id": 1, "verdict": "refuted", "reason": "  "}))

    def test_non_int_id(self):
        self.assertIsNotNone(vi.validate_entry(
            {"opportunity_id": "1", "verdict": "refuted", "reason": "x"}))


class TestIngest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.db = os.path.join(d, "t.db")
        self.log_dir = os.path.join(d, "verify_log")
        os.makedirs(self.log_dir)
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE opportunities (id INTEGER PRIMARY KEY, status TEXT)")
        conn.executemany("INSERT INTO opportunities VALUES (?, ?)",
                         [(1, "verified"), (2, "refuted"), (3, "open")])
        conn.commit(); conn.close()
        self.pending = os.path.join(d, ".pending_test.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _write_pending(self, entries):
        with open(self.pending, "w") as f:
            json.dump(entries, f)

    def test_ingest_appends_valid_quarantines_bad(self):
        self._write_pending([
            {"opportunity_id": 1, "verdict": "confirmed", "reason": "ok"},
            {"opportunity_id": 2, "verdict": "refuted", "reason": "fake"},
            {"opportunity_id": 3, "verdict": "bogus", "reason": "x"},      # 坏 verdict → quarantine
            {"opportunity_id": "x", "verdict": "confirmed", "reason": "y"}, # 坏 id → quarantine
        ])
        rc = vi.ingest(self.pending, [1, 2, 3, 4], db_path=self.db, log_dir=self.log_dir)
        self.assertEqual(rc, 0)
        logs = [json.loads(l) for f in os.listdir(self.log_dir) if f.endswith(".jsonl") and f != "quarantine.jsonl"
                for l in open(os.path.join(self.log_dir, f))]
        self.assertEqual(len(logs), 2)
        self.assertTrue(all(l["source"] == "verify" for l in logs))
        quar = [json.loads(l) for l in open(os.path.join(self.log_dir, "quarantine.jsonl"))]
        self.assertEqual(len(quar), 2)

    def test_audit_missing_verdict_warns(self):
        self._write_pending([{"opportunity_id": 1, "verdict": "confirmed", "reason": "ok"}])
        rc = vi.ingest(self.pending, [1, 2], db_path=self.db, log_dir=self.log_dir)
        self.assertEqual(rc, 0)   # 漏判只 WARN 不失败

    def test_missing_pending_file(self):
        rc = vi.ingest(os.path.join(self.tmp.name, "nope.json"), [1],
                       db_path=self.db, log_dir=self.log_dir)
        self.assertEqual(rc, 0)   # verify CLI 失败时 pending 不存在，WARN 但不炸

    def test_dry_run_writes_nothing(self):
        self._write_pending([{"opportunity_id": 1, "verdict": "confirmed", "reason": "ok"}])
        rc = vi.ingest(self.pending, [1], db_path=self.db, log_dir=self.log_dir, dry_run=True)
        self.assertEqual(rc, 0)
        self.assertEqual([f for f in os.listdir(self.log_dir) if f.endswith(".jsonl")], [])
