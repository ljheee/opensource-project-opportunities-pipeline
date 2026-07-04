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


if __name__ == "__main__":
    unittest.main()
