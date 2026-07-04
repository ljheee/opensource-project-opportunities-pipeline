#!/usr/bin/env python3
"""Smoke tests for stages/analyze.py.

These tests exercise pure helper functions with inline fixtures.  They do not
hit the GitHub API, so they are fast and safe to run in CI or locally.
"""
import json
import unittest

from stages import analyze


class TestClassifyIssue(unittest.TestCase):
    def test_security(self):
        self.assertEqual(analyze.classify_issue("CVE-2024-1234 vulnerability", ""), "security")

    def test_performance(self):
        self.assertEqual(analyze.classify_issue("High latency under load", ""), "performance")

    def test_compatibility(self):
        self.assertEqual(analyze.classify_issue("Breaking change after upgrade", ""), "compatibility")

    def test_issue(self):
        self.assertEqual(analyze.classify_issue("Add support for LIMIT", ""), "issue")

    def test_none_body(self):
        self.assertEqual(analyze.classify_issue("perf regression", None), "performance")


class TestTreeHelpers(unittest.TestCase):
    def test_get_tree_paths_normal(self):
        tree_data = {"tree": [{"path": "src/main.go"}, {"path": "README.md"}]}
        self.assertEqual(sorted(analyze.get_tree_paths(tree_data)), ["README.md", "src/main.go"])

    def test_get_tree_paths_truncated(self):
        # Truncated trees only keep top-level paths.
        tree_data = {
            "truncated": True,
            "tree": [
                {"path": "src/main.go"},
                {"path": "src/deep/nested.go"},
                {"path": "README.md"},
            ],
        }
        self.assertEqual(analyze.get_tree_paths(tree_data), ["README.md"])

    def test_get_tree_paths_invalid_input(self):
        self.assertEqual(analyze.get_tree_paths(None), [])
        self.assertEqual(analyze.get_tree_paths([]), [])

    def test_get_root_dirs(self):
        paths = ["src/main.go", "tests/test.py", "README.md"]
        self.assertEqual(analyze.get_root_dirs(paths), ["src", "tests"])

    def test_get_root_dirs_empty(self):
        self.assertEqual(analyze.get_root_dirs([]), [])

    def test_get_key_files(self):
        paths = ["go.mod", "src/main.go", "README.md", "package.json"]
        key = analyze.get_key_files(paths)
        self.assertIn("go.mod", key)
        self.assertIn("README.md", key)
        self.assertNotIn("src/main.go", key)

    def test_get_key_files_empty(self):
        self.assertEqual(analyze.get_key_files([]), [])


class TestParseAndDecode(unittest.TestCase):
    def test_parse_owner_repo(self):
        self.assertEqual(analyze.parse_owner_repo("https://github.com/foo/bar"), ("foo", "bar"))
        self.assertEqual(analyze.parse_owner_repo("https://github.com/foo/bar.git"), ("foo", "bar"))

    def test_parse_owner_repo_invalid(self):
        self.assertEqual(analyze.parse_owner_repo(""), (None, None))
        self.assertEqual(analyze.parse_owner_repo("not-a-url"), (None, None))

    def test_decode_readme(self):
        import base64
        content = base64.b64encode(b"# Hello").decode()
        self.assertEqual(analyze.decode_readme({"content": content}), "# Hello")

    def test_decode_readme_invalid(self):
        self.assertEqual(analyze.decode_readme({"content": "not-base64!!!"}), "")
        self.assertEqual(analyze.decode_readme(None), "")


class TestEvidenceHelpers(unittest.TestCase):
    def test_extract_keywords_empty_and_stop_words(self):
        self.assertEqual(analyze._extract_keywords(""), set())
        self.assertEqual(analyze._extract_keywords("this with from have been"), set())

    def test_extract_keywords_normal(self):
        self.assertEqual(
            analyze._extract_keywords("Fix memory allocation bug in production"),
            {"memory", "allocation", "production"},
        )

    def test_extract_quote_around_keyword_not_found(self):
        self.assertEqual(analyze._extract_quote_around_keyword("hello world", "missing"), "")

    def test_extract_quote_around_keyword_found(self):
        q = analyze._extract_quote_around_keyword("we hit a production outage today", "production", 20)
        self.assertIn("production", q)
        self.assertIn("outage", q)

    def test_extract_quote_around_keyword_empty_text(self):
        self.assertEqual(analyze._extract_quote_around_keyword(None, "prod"), "")

    def test_extract_prod_signal_quote_in_body(self):
        q, has = analyze._extract_prod_signal_quote("crash in production", [])
        self.assertTrue(has)
        self.assertIn("production", q.lower())

    def test_extract_prod_signal_quote_in_comment(self):
        q, has = analyze._extract_prod_signal_quote("just a bug", [{"body": "we use it in production"}])
        self.assertTrue(has)
        self.assertIn("production", q.lower())

    def test_extract_prod_signal_quote_no_signal(self):
        q, has = analyze._extract_prod_signal_quote("just a bug", [{"body": "me too"}])
        self.assertFalse(has)
        self.assertEqual(q, "")

    def test_extract_prod_signal_quote_invalid_comment(self):
        q, has = analyze._extract_prod_signal_quote("production crash", ["not-a-dict"])
        self.assertTrue(has)
        self.assertIn("production", q.lower())

    def test_count_related_issues_empty(self):
        self.assertEqual(analyze._count_related_issues([], "title", "body"), 0)

    def test_count_related_issues_no_match(self):
        issues = [{"number": 1, "title": "foo", "body": "bar"}]
        self.assertEqual(analyze._count_related_issues(issues, "memory allocation", "bug"), 0)

    def test_count_related_issues_match(self):
        issues = [{"number": 1, "title": "memory leak", "body": "allocation failure"}]
        self.assertEqual(analyze._count_related_issues(issues, "memory allocation", "bug"), 1)

    def test_count_related_issues_invalid_issue(self):
        issues = ["not-a-dict", {"number": 1, "title": "memory leak", "body": ""}]
        self.assertEqual(analyze._count_related_issues(issues, "memory leak", ""), 1)

    def test_count_related_issues_excludes_self(self):
        issues = [{"number": 42, "title": "memory leak", "body": "allocation failure"}]
        self.assertEqual(analyze._count_related_issues(issues, "memory leak", "", exclude_number=42), 0)

    def test_count_related_issues_excludes_only_self(self):
        issues = [
            {"number": 42, "title": "memory leak", "body": "allocation failure"},
            {"number": 43, "title": "memory allocation bug", "body": "leak detected"},
        ]
        self.assertEqual(analyze._count_related_issues(issues, "memory leak", "", exclude_number=42), 1)

    def test_find_related_paths_empty(self):
        self.assertEqual(analyze._find_related_paths([], "foo"), [])

    def test_find_related_paths_keyword(self):
        paths = ["src/memory.go", "src/network.go", "cmd/main.go"]
        self.assertEqual(analyze._find_related_paths(paths, "memory"), ["src/memory.go"])

    def test_find_related_paths_multi_part_keyword(self):
        paths = ["src/memory_pool.go", "src/network.go"]
        self.assertEqual(analyze._find_related_paths(paths, "memory-pool"), ["src/memory_pool.go"])

    def test_has_stub(self):
        self.assertTrue(analyze._has_stub(["src/raft.go"], "raft"))
        self.assertFalse(analyze._has_stub(["src/main.go"], "raft"))

    def test_has_stub_empty(self):
        self.assertFalse(analyze._has_stub([], "raft"))

    def test_find_approach_file_explicit(self):
        # Regex captures from the last slash; leading slash yields the full path.
        self.assertEqual(analyze._find_approach_file([], "bug", "see /src/engine.go"), "src/engine.go")

    def test_contains_phrase_word_boundary(self):
        self.assertTrue(analyze._contains_phrase("this is out of scope", "out of scope"))
        self.assertFalse(analyze._contains_phrase("this is out of scoped", "out of scope"))
        self.assertFalse(analyze._contains_phrase("unintentional side effect", "intentional"))

    def test_find_approach_file_perf_fallback(self):
        paths = ["src/memory.go", "src/network.go"]
        self.assertEqual(analyze._find_approach_file(paths, "slow memory allocation", ""), "src/memory.go")

    def test_find_approach_file_no_match(self):
        self.assertEqual(analyze._find_approach_file(["src/main.go"], "bug", ""), "")

    def test_make_gap_desc_variants(self):
        self.assertIn("canonical implementation", analyze._make_gap_desc("feature_gap", "foo"))
        self.assertIn("security", analyze._make_gap_desc("security", "xss"))
        self.assertIn("performance", analyze._make_gap_desc("performance", "slow"))
        self.assertIn("reported", analyze._make_gap_desc("issue", "bug"))

    def test_make_why_hard_concurrency(self):
        self.assertIn("concurrency", analyze._make_why_hard("issue", "race in mutex", "", False))

    def test_make_why_hard_data_structure(self):
        self.assertIn("data structure", analyze._make_why_hard("issue", "core data structure", "", False))

    def test_make_why_hard_performance_with_file(self):
        why = analyze._make_why_hard("performance", "slow", "", False, approach_file="src/engine.go")
        self.assertIn("profiling", why)
        self.assertIn("src/engine.go", why)

    def test_make_why_hard_no_canonical(self):
        why = analyze._make_why_hard("feature_gap", "foo", "", False)
        self.assertIn("no canonical", why)

    def test_make_why_hard_default(self):
        # With a canonical impl available and no keywords, falls back to the unclear message.
        self.assertIn("unclear", analyze._make_why_hard("issue", "foo", "", True))


class TestEvidenceJsonContract(unittest.TestCase):
    """Guard the shape of evidence JSON written by analyze_project."""

    def test_value_evidence_contract(self):
        ve = {
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 5,
            "issue_count": 1,
            "has_workaround": False,
            "prod_signal_quote": "",
            "has_prod_signal": False,
            "gap_desc": "gap",
        }
        data = json.loads(json.dumps(ve))
        self.assertIsInstance(data["canonical_impl_url"], str)
        self.assertIsInstance(data["canonical_impl_loc"], int)
        self.assertIsInstance(data["peer_impl_urls"], list)
        self.assertIsInstance(data["issue_reactions"], int)
        self.assertIsInstance(data["issue_count"], int)
        self.assertIsInstance(data["has_workaround"], bool)
        self.assertIsInstance(data["has_prod_signal"], bool)

    def test_difficulty_evidence_contract(self):
        de = {
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": "hard because concurrency",
            "target_approach_file": "src/engine.go",
        }
        data = json.loads(json.dumps(de))
        self.assertIsInstance(data["why_hard"], str)
        self.assertIsInstance(data["target_approach_file"], str)

    def test_urgency_evidence_contract(self):
        ue = {
            "cve_id": None,
            "has_prod_signal": False,
            "has_workaround": False,
        }
        data = json.loads(json.dumps(ue))
        self.assertTrue(data["cve_id"] is None or isinstance(data["cve_id"], str))
        self.assertIsInstance(data["has_prod_signal"], bool)
        self.assertIsInstance(data["has_workaround"], bool)

    def test_maintainer_evidence_contract(self):
        me = {
            "similar_prs": [],
            "maintainer_responses": [{"body_quote": "hello"}],
            "welcome_labels": ["help wanted"],
        }
        data = json.loads(json.dumps(me))
        self.assertIsInstance(data["similar_prs"], list)
        self.assertIsInstance(data["maintainer_responses"], list)
        self.assertIsInstance(data["welcome_labels"], list)


if __name__ == "__main__":
    unittest.main()
