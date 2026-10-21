#!/usr/bin/env python3
"""Welcome-label matching: decorated spellings, and the self-apply hazard.

2026-10-20: eight genuinely welcoming labels were scored `unknown` because the
matcher compared raw strings. The fix normalises decoration (emoji, namespace
prefix, hyphen, plural) — but only for the explicitly-welcoming words. The weak
set (`enhancement` and friends) stays exact-match, because reporters routinely
apply those themselves; normalising them would turn 'type: enhancement' and
'⭐ enhancement' into fake welcome signals.
"""
import unittest

from stages import analyze, scoring


class TestWelcomeLabelNormalisation(unittest.TestCase):
    """Decorated welcome labels must still be recognised."""

    def test_decorated_welcome_labels_match(self):
        for label in (
            "❓ help wanted",            # emoji prefix
            "E-help-wanted",            # single-letter topic prefix
            "Contribution Welcome",     # singular where the vocabulary is plural
            "contribution welcome",
            "Open Source Contributors Welcomed",
            "needs contributor",
            "status: volunteer wanted",  # namespace prefix
            "first-issue",
        ):
            with self.subTest(label=label):
                self.assertTrue(scoring.is_welcome_label(label),
                                f"{label!r} should be recognised as welcome")

    def test_plain_welcome_labels_still_match(self):
        for label in ("help wanted", "good first issue", "pr welcome",
                      "contributions welcome", "pull request welcome",
                      "enhancement", "feature-request", "accepted"):
            with self.subTest(label=label):
                self.assertTrue(scoring.is_welcome_label(label))

    def test_non_welcome_labels_do_not_match(self):
        for label in ("feature", "bug", "question", "triage", "roadmap",
                      "documentation", "priority-high", "kind::feature",
                      "part: documentation", "change:planned", "stale",
                      "needs design before approval (status:approved required)"):
            with self.subTest(label=label):
                self.assertFalse(scoring.is_welcome_label(label))

    def test_decorated_weak_labels_stay_exact_match_only(self):
        """A decorated 'enhancement' is still the self-applied label it always was.

        Reporters routinely label their own issue `enhancement`; if normalisation
        reached that word, every such row would fake a `welcoming` signal and get
        promoted a level by score_value.
        """
        for label in ("type: enhancement", "Type: Enhancement", "⭐ enhancement"):
            with self.subTest(label=label):
                self.assertFalse(scoring.is_welcome_label(label),
                                 f"{label!r} must not become a welcome signal")

    def test_empty_and_non_string_labels_are_safe(self):
        for label in (None, "", "   ", 123, [], {}):
            with self.subTest(label=label):
                self.assertFalse(scoring.is_welcome_label(label))

    def test_a_label_named_welcome_is_not_a_welcome_signal(self):
        """Regression: stripping a short leading token collapsed 'pr welcome' to
        'welcome', so a repo whose label is literally 'Welcome' matched."""
        for label in ("Welcome", "welcome", "Welcome to the project"):
            with self.subTest(label=label):
                self.assertFalse(scoring.is_welcome_label(label))

    def test_pr_welcome_still_matches(self):
        for label in ("pr welcome", "pr-welcome", "PR Welcome", "pull request welcome"):
            with self.subTest(label=label):
                self.assertTrue(scoring.is_welcome_label(label))


class TestProducerConsumerContract(unittest.TestCase):
    """analyze.py produces welcome_labels; scoring.py consumes them."""

    def test_collect_accepts_everything_the_consumer_accepts(self):
        """The producer must never be narrower than the consumer."""
        for label in ("❓ help wanted", "E-help-wanted", "Contribution Welcome",
                      "status: volunteer wanted", "needs contributor", "first-issue",
                      "Open Source Contributors Welcomed", "help wanted"):
            with self.subTest(label=label):
                self.assertEqual(analyze._collect_welcome_labels([label]), [label])

    def test_collect_drops_the_raw_label_list(self):
        """The refine stage used to dump the whole label list into welcome_labels."""
        self.assertEqual(
            analyze._collect_welcome_labels(["feature", "bug", "question", "triage"]),
            [])

    def test_collect_keeps_original_casing(self):
        self.assertEqual(
            analyze._collect_welcome_labels(["Help Wanted", "help wanted", "LGTM"]),
            ["Help Wanted", "help wanted"])

    def test_both_sides_use_the_same_implementation(self):
        """Importing 'scoring' as a top-level module would load a second copy."""
        self.assertIs(analyze.is_welcome_label, scoring.is_welcome_label)


class TestWelcomeSignalScoring(unittest.TestCase):
    def test_decorated_label_produces_welcoming_signal(self):
        me = {"welcome_labels": ["❓ help wanted"], "maintainer_responses": [],
              "similar_prs": []}
        self.assertEqual(scoring.score_maintainer_signal(me), "welcoming")

    def test_self_applied_enhancement_does_not_produce_welcoming(self):
        me = {"welcome_labels": ["type: enhancement"], "maintainer_responses": [],
              "similar_prs": []}
        self.assertEqual(scoring.score_maintainer_signal(me), "unknown")

    def test_welcoming_promotes_value_by_one_level(self):
        """The promoting path itself — a welcome label lifts a low-value row."""
        ve = {"canonical_impl_url": "", "issue_reactions": 0}
        self.assertEqual(scoring.score_value(ve, "unknown", "issue", False), "low")
        self.assertEqual(scoring.score_value(ve, "welcoming", "issue", False), "medium")
