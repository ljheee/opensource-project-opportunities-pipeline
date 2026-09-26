#!/usr/bin/env python3
"""Regression tests for the four defects found during the 2026-09-25 draft refinement."""
import unittest

from stages import analyze, scoring


class TestWelcomeLabelContract(unittest.TestCase):
    """P0-1: analyze.py collected 4 welcome labels, scoring.py consumed 10."""

    def test_analyze_collects_every_label_scoring_consumes(self):
        self.assertTrue(
            scoring._WELCOME_LABELS.issubset(analyze.WELCOME_LABELS),
            f"analyze.py is missing: {sorted(scoring._WELCOME_LABELS - analyze.WELCOME_LABELS)}")

    def test_enhancement_is_collected(self):
        self.assertIn("enhancement", analyze.WELCOME_LABELS)
        self.assertEqual(analyze._collect_welcome_labels(["enhancement", "bug"]), ["enhancement"])
        self.assertEqual(analyze._collect_welcome_labels(["accepted"]), ["accepted"])

    def test_collect_is_case_insensitive_and_keeps_original_case(self):
        self.assertEqual(
            analyze._collect_welcome_labels(["Help Wanted", "help wanted", "LGTM"]),
            ["Help Wanted", "help wanted"])


class TestHasCanonicalIsNotHardcoded(unittest.TestCase):
    """P0-2: analyze.py passed has_canonical=False for every issue draft, so projects
    that DO have a canonical still asserted 'no canonical reference' in their evidence."""

    def test_issue_draft_with_canonical_does_not_claim_no_reference(self):
        self.assertNotIn("no canonical reference",
                         analyze._make_why_hard("issue", "Add retry budget", "b", has_canonical=True))

    def test_issue_draft_without_canonical_still_says_so(self):
        self.assertIn("no canonical reference",
                      analyze._make_why_hard("issue", "Add retry budget", "b", has_canonical=False))

    def test_removing_the_false_claim_does_not_change_difficulty(self):
        """score_difficulty's own no-canonical fallback is already `base = "high"`,
        so this fix corrects a false statement without moving any score."""
        de = {"canonical_impl_url": "", "canonical_impl_loc": 0, "target_approach_file": ""}
        self.assertEqual(
            scoring.score_difficulty(dict(de, why_hard="Hard because: no canonical reference implementation available for guidance")),
            "high")
        self.assertEqual(
            scoring.score_difficulty(dict(de, why_hard="Implementation effort unclear without deeper investigation.")),
            "high")


class TestEvidenceJsonTolerance(unittest.TestCase):
    """P0-3: unescaped quotes / raw control chars in LLM-written evidence made
    json.loads raise, and scoring skipped the whole opportunity."""

    def test_unescaped_quote_does_not_raise(self):
        self.assertEqual(scoring._loads_evidence('{"why_hard": "he said "hi" loudly"}'), {})

    def test_control_character_does_not_raise(self):
        self.assertEqual(scoring._loads_evidence('{"why_hard": "a\x0cb"}'), {})

    def test_valid_json_still_parses(self):
        self.assertEqual(scoring._loads_evidence('{"why_hard": "ok"}'), {"why_hard": "ok"})

    def test_none_and_empty_tolerated(self):
        self.assertEqual(scoring._loads_evidence(None), {})
        self.assertEqual(scoring._loads_evidence(""), {})

    def test_non_dict_coerced(self):
        self.assertEqual(scoring._loads_evidence("[1,2,3]"), {})


class TestMaintainerDetectionIncludesContributors(unittest.TestCase):
    """P1-1/P1-2: OWNER/MEMBER/COLLABORATOR only, so company-project founders reporting
    as CONTRIBUTOR were dropped — including restate's 'flow control shipped in v1.7'."""

    def test_contributor_counts(self):
        self.assertTrue(analyze.is_maintainer_signal("CONTRIBUTOR"))

    def test_stranger_does_not(self):
        self.assertFalse(analyze.is_maintainer_signal("NONE"))

    def test_owner_member_collaborator_still_count(self):
        for a in ("OWNER", "MEMBER", "COLLABORATOR"):
            self.assertTrue(analyze.is_maintainer_signal(a), a)

    def test_maintainer_past_comment_ten_is_not_missed(self):
        comments = [{"author_association": "NONE", "body": f"chatter {i}"} for i in range(12)]
        comments.append({"author_association": "OWNER", "body": "I'll take this one"})
        picked = analyze.collect_maintainer_responses(comments)
        self.assertTrue(any("I'll take this one" in p["body_quote"] for p in picked),
                        "maintainer comment beyond index 10 was dropped")

    def test_high_confidence_outranks_contributor(self):
        picked = analyze.collect_maintainer_responses([
            {"author_association": "CONTRIBUTOR", "body": "contributor noise"},
            {"author_association": "OWNER", "body": "owner decision"},
        ])
        self.assertEqual(picked[0]["body_quote"], "owner decision")
        self.assertEqual(picked[0]["author_association"], "OWNER")

    def test_association_recorded_for_downstream_weighting(self):
        picked = analyze.collect_maintainer_responses(
            [{"author_association": "CONTRIBUTOR", "body": "flow control shipped in v1.7"}])
        self.assertEqual(picked[0]["author_association"], "CONTRIBUTOR")

    def test_shipped_announcement_outranks_routine_reply(self):
        """restate#3291: the maintainer announcing "released with v1.7" sat at index 5 and
        was cut by the 2-response cap, while two earlier 'thanks for the feedback' replies
        survived. The decision-carrying comment must win the slot."""
        comments = [
            {"author_association": "CONTRIBUTOR", "body": "Hi, thanks for the feedback!"},
            {"author_association": "CONTRIBUTOR", "body": "Thanks, that is helpful."},
            {"author_association": "CONTRIBUTOR", "body": "good catch"},
            {"author_association": "CONTRIBUTOR", "body": "much appreciated"},
            {"author_association": "CONTRIBUTOR", "body": "great, thanks"},
            {"author_association": "CONTRIBUTOR",
             "body": "The first flow control features have been released with v1.7"},
        ]
        picked = analyze.collect_maintainer_responses(comments)
        self.assertIn("released with v1.7", picked[0]["body_quote"])

    def test_refusal_also_outranks_routine_reply(self):
        comments = [
            {"author_association": "MEMBER", "body": "thanks, looking into it"},
            {"author_association": "MEMBER", "body": "thanks again"},
            {"author_association": "MEMBER", "body": "we are not considering new SDKs"},
        ]
        picked = analyze.collect_maintainer_responses(comments)
        self.assertIn("not considering new SDKs", picked[0]["body_quote"])


if __name__ == "__main__":
    unittest.main()
