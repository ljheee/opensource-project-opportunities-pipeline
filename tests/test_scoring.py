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
                source_type TEXT, source_ref TEXT, issue_number INTEGER,
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


class TestMergedPrIsNotAWelcomeSignal(unittest.TestCase):
    """merged PR 曾经被当成「维护者欢迎外部贡献」的信号。

    similar_prs 来自 analyze.py 的模糊搜索 `repo:X is:pr is:merged "<标题前 40 字>"`，
    命中的是「标题里碰巧有共同词」的 PR——实测大量是 dependabot 升级
    （"chore(wren-ai-service): bump the all group … with 25 updates"）。
    而当 merged PR **真的**相关时，它指向的是反面：诉求已被交付
    （bytewax#558 的 PR 标题逐字回答了诉求）。同一个事实被两层算成了两个相反的信号。
    """

    def test_merged_pr_alone_is_not_welcoming(self):
        me = {"similar_prs": [{"merged": True, "age_days": 10}]}
        self.assertNotEqual(scoring.score_maintainer_signal(me), "welcoming")

    def test_merged_pr_alone_yields_unknown(self):
        me = {"similar_prs": [{"merged": True, "age_days": 10}]}
        self.assertEqual(scoring.score_maintainer_signal(me), "unknown")

    def test_placeholder_pr_without_number_is_not_welcoming(self):
        """无 number/title/url 的占位条目最恶劣：连回溯审计的入口都没有。"""
        me = {"similar_prs": [{"merged": True, "age_days": 92},
                              {"merged": True, "age_days": 886}]}
        self.assertEqual(scoring.score_maintainer_signal(me), "unknown")

    def test_welcome_label_still_works_alongside_merged_pr(self):
        me = {"similar_prs": [{"merged": True, "age_days": 10}],
              "welcome_labels": ["help wanted"]}
        self.assertEqual(scoring.score_maintainer_signal(me), "welcoming")

    def test_maintainer_invitation_still_works(self):
        me = {"maintainer_responses": [
            {"body_quote": "PRs are welcome, feel free to send one"}]}
        self.assertEqual(scoring.score_maintainer_signal(me), "welcoming")

    def test_rejection_via_maintainer_comment_still_works(self):
        me = {"similar_prs": [{"merged": False, "age_days": 5,
                               "maintainer_comment": "this is out of scope"}]}
        self.assertEqual(scoring.score_maintainer_signal(me), "rejected")

    def test_removing_the_merged_signal_does_not_penalise_the_row(self):
        """修复不是把行判死：证据里的 welcoming 仍照常抬 value。"""
        me = {"similar_prs": [{"merged": True, "age_days": 10}],
              "welcome_labels": ["good first issue"]}
        signal = scoring.score_maintainer_signal(me)
        ve = {"canonical_impl_url": "https://github.com/x/y/blob/main/a.go"}
        self.assertEqual(signal, "welcoming")
        self.assertEqual(scoring.score_value(ve, signal), "high")

    def test_response_body_field_fallback(self):
        """历史行（含 v3 verify 写入的）只写 body，不写 body_quote。"""
        me = {"maintainer_responses": [
            {"body": "out of scope, this is by design"}]}
        self.assertEqual(scoring.score_maintainer_signal(me), "rejected")


class TestShippedVocabulary(unittest.TestCase):
    """维护者宣布「已交付」的表述此前整条链路无人识别。"""

    def test_release_announcement_is_shipped(self):
        me = {"maintainer_responses": [
            {"body_quote": "The first flow control features have been released with v1.7"}]}
        self.assertEqual(scoring.score_maintainer_signal(me), "shipped")

    def test_fixed_in_version_is_shipped(self):
        me = {"maintainer_responses": [{"body_quote": "fixed in v310"}]}
        self.assertEqual(scoring.score_maintainer_signal(me), "shipped")

    def test_future_release_is_not_shipped(self):
        me = {"maintainer_responses": [
            {"body_quote": "once it is released, we'll be able to add this"}]}
        self.assertEqual(scoring.score_maintainer_signal(me), "unknown")

    def test_negated_release_is_not_shipped(self):
        me = {"maintainer_responses": [
            {"body_quote": "as the 1.5.0 is still not released, please pin 1.4.0"}]}
        self.assertEqual(scoring.score_maintainer_signal(me), "unknown")

    def test_hedged_statement_is_not_shipped(self):
        me = {"maintainer_responses": [
            {"body_quote": "It's possible this issue has been fixed in the latest release. "
                          "If you can verify and let us know whether this is still an issue"}]}
        self.assertEqual(scoring.score_maintainer_signal(me), "unknown")

    def test_local_patch_without_commit_is_not_shipped(self):
        me = {"maintainer_responses": [
            {"body_quote": "I've already fixed this :) The patch was a bit messy "
                          "so I did not commit it to 2.10"}]}
        self.assertEqual(scoring.score_maintainer_signal(me), "unknown")

    def test_delivery_of_another_issue_is_not_shipped(self):
        me = {"maintainer_responses": [
            {"body_quote": "that one was snapshot retention and was fixed by #1325 in v0.5.14, "
                          "while this is EnforceL0RetentionByTime"}]}
        self.assertEqual(scoring.score_maintainer_signal(me, own_issue=1270), "unknown")

    def test_delivery_of_own_issue_is_shipped(self):
        me = {"maintainer_responses": [{"body_quote": "the problem was fixed in #4113"}]}
        self.assertEqual(scoring.score_maintainer_signal(me, own_issue=4113), "shipped")

    def test_shipped_does_not_kill_the_row(self):
        """shipped 是可见信号，不是判死：scoring.py 看不到诉求正文，
        维护者也可能一边宣布功能已发布、一边邀请补文档。裁决留给 verify 阶段。"""
        me = {"maintainer_responses": [
            {"body_quote": "The first flow control features have been released with v1.7"}]}
        signal = scoring.score_maintainer_signal(me)
        self.assertEqual(signal, "shipped")
        self.assertEqual(scoring._writeback_status(signal, "open"), "open")
        self.assertEqual(scoring._writeback_status(signal, "verified"), "verified")

    def test_shipped_outranks_welcoming(self):
        me = {"maintainer_responses": [
            {"body_quote": "has been implemented already, and feel free to send docs fixes"}]}
        self.assertEqual(scoring.score_maintainer_signal(me), "shipped")


if __name__ == "__main__":
    unittest.main()
