#!/usr/bin/env python3
"""Smoke tests for stages/validate.py（网络层全部 fake，不打真实 API）。"""
import unittest

from stages import validate as v


class TestParseIssueRef(unittest.TestCase):
    def test_short_format(self):
        self.assertEqual(v.parse_issue_ref("issue:507", "connectrpc/connect-es"),
                         ("connectrpc/connect-es", 507))

    def test_full_url(self):
        self.assertEqual(v.parse_issue_ref(
            "https://github.com/sqlalchemy/alembic/issues/278", "x/y"),
            ("sqlalchemy/alembic", 278))

    def test_canonical_ref_returns_none(self):
        self.assertIsNone(v.parse_issue_ref("canonical:Java/license", "o/r"))

    def test_trailing_slash_rejected(self):
        # 严格匹配：带尾斜杠/查询串的旧脏数据不解析，留给人工
        self.assertIsNone(v.parse_issue_ref(
            "https://github.com/o/r/issues/1/", "o/r"))


class TestParseBlobUrl(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(
            v.parse_blob_url("https://github.com/alibaba/Sentinel/blob/master/sentinel-core/x.java"),
            ("alibaba/Sentinel", "master", "sentinel-core/x.java"))

    def test_repo_homepage_returns_none(self):
        self.assertIsNone(v.parse_blob_url("https://github.com/o/r"))
        self.assertIsNone(v.parse_blob_url(""))

    def test_tree_url_returns_none(self):
        self.assertIsNone(v.parse_blob_url("https://github.com/o/r/tree/main/pkg"))


class FakeGh:
    """模拟 gh_get：按 path 返回 (status, json)。"""
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, path, params=None):
        self.calls.append(path)
        return self.routes.get(path, (404, None))


class TestValidateRow(unittest.TestCase):
    def _row(self, **kw):
        base = {"id": 1, "project_id": "o/r", "source_type": "issue",
                "source_ref": "issue:42", "status": "verified",
                "value_evidence": "{}", "difficulty_evidence": "{}",
                "urgency_evidence": "{}", "maintainer_evidence": "{}"}
        base.update(kw)
        return base

    def test_closed_issue_refutes(self):
        gh = FakeGh({"/repos/o/r/issues/42": (200, {"state": "closed"})})
        actions = v.validate_row(self._row(), gh, lambda e: None)
        self.assertIn("refute:issue-closed", actions)

    def test_open_issue_survives(self):
        gh = FakeGh({"/repos/o/r/issues/42": (200, {"state": "open", "labels": []})})
        actions = v.validate_row(self._row(), gh, lambda e: None)
        self.assertEqual(actions, [])

    def test_phantom_label_stripped(self):
        gh = FakeGh({"/repos/o/r/issues/42": (200, {"state": "open", "labels": []})})
        row = self._row(maintainer_evidence='{"welcome_labels": ["help wanted"], "similar_prs": []}')
        actions = v.validate_row(row, gh, lambda e: None)
        self.assertIn("strip:welcome_labels", actions)

    def test_canonical_url_404_blanked(self):
        gh = FakeGh({"/repos/o/r/issues/42": (200, {"state": "open", "labels": []})})
        row = self._row(value_evidence='{"canonical_impl_url": "https://github.com/a/b/blob/main/x.go"}')
        actions = v.validate_row(row, gh, lambda e: None)
        self.assertIn("blank:canonical_impl_url", actions)

    def test_feature_gap_without_verification_refuted(self):
        gh = FakeGh({})
        row = self._row(source_type="feature_gap", source_ref="canonical:Java/x",
                        value_evidence="{}", status="open")
        actions = v.validate_row(row, gh, lambda e: None)
        self.assertIn("refute:no-feature-verification", actions)

    def test_feature_gap_verified_exempt(self):
        gh = FakeGh({})
        row = self._row(source_type="feature_gap", source_ref="canonical:Java/x",
                        value_evidence="{}")
        actions = v.validate_row(row, gh, lambda e: None)
        self.assertEqual(actions, [])

    def test_api_error_skips_without_action(self):
        gh = FakeGh({"/repos/o/r/issues/42": (429, None)})
        actions = v.validate_row(self._row(), gh, lambda e: None)
        self.assertEqual(actions, ["skip:api-error"])

    def test_issue_403_skips(self):
        # 未认证限流/secondary rate limit 常返回 403：按 API 错误跳过，不误杀
        gh = FakeGh({"/repos/o/r/issues/42": (403, None)})
        actions = v.validate_row(self._row(), gh, lambda e: None)
        self.assertEqual(actions, ["skip:api-error"])

    def test_pull_403_keeps_pr(self):
        gh = FakeGh({"/repos/o/r/issues/42": (200, {"state": "open", "labels": []}),
                     "/repos/o/r/pulls/7": (403, None)})
        row = self._row(maintainer_evidence='{"similar_prs": [{"number": 7, "merged": true}]}')
        actions = v.validate_row(row, gh, lambda e: None)
        self.assertNotIn("strip:similar_prs", actions)
