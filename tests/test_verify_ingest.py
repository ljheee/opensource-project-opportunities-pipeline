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


# --- checks / corrections 受控词表 (2026-09-27) ---

from stages.verify_ingest import (CHECK_VOCAB, _CHECK_ALIASES,
                                   normalise_check, normalise_correction)


class TestCheckVocabulary(unittest.TestCase):
    """历史上 3605 次 checks 出现散成 1352 种写法，727 次连前缀都没有，
    机器无法聚合。词表按 verify_v3.md 实际定义的核查项制定。"""

    def test_vocabulary_covers_every_prompt_defined_check(self):
        for k in ("meta_discussion", "issue_state", "issue_labels", "linked_pr",
                  "reactions_calibration", "similar_prs", "code_search",
                  "canonical_url", "cve_format", "affected_file"):
            self.assertIn(k, CHECK_VOCAB, k)

    def test_canonical_form_is_returned_unchanged(self):
        self.assertEqual(normalise_check("issue_state:closed"), "issue_state:closed")

    def test_case_and_space_insensitive(self):
        self.assertEqual(normalise_check("Issue_State: closed"), "issue_state:closed")
        self.assertEqual(normalise_check("  issue_state:closed  "), "issue_state:closed")

    def test_bare_name_is_accepted_as_pass(self):
        self.assertEqual(normalise_check("issue_state"), "issue_state:pass")

    def test_known_aliases_collapse_to_canonical(self):
        # 这四种写法在历史日志里都出现过，语义完全相同
        for raw in ("issue_state:open", "issue:open", "issue:state=open", "state:open"):
            self.assertEqual(normalise_check(raw), "issue_state:open", raw)

    def test_timeline_aliases_collapse(self):
        for raw in ("timeline:no cross-referenced PR", "timeline:无cross-referenced",
                    "linked_pr:none", "linked_prs:none"):
            self.assertEqual(normalise_check(raw), "linked_pr:none", raw)

    def test_unknown_prefix_is_preserved_not_dropped(self):
        """词表外的检查项不应被静默丢弃——判据未知时保留原文，
        宁可分析时看见噪音，也不要悄悄少一条证据。"""
        out = normalise_check("some_future_check:xyz")
        self.assertEqual(out, "some_future_check:xyz")

    def test_non_string_check_becomes_readable(self):
        self.assertEqual(normalise_check({"a": 1}), "{'a': 1}")


class TestCorrectionVocabulary(unittest.TestCase):
    def test_bare_string_passes_through(self):
        self.assertEqual(normalise_correction("blank:canonical_impl_url"),
                         "blank:canonical_impl_url")

    def test_dict_collapsed_to_stable_text(self):
        out = normalise_correction({"field": "value_evidence.gap_desc", "new": "x"})
        self.assertIn("value_evidence.gap_desc", out)
        self.assertIn("x", out)

    def test_both_shapes_normalise_to_the_same_string_type(self):
        self.assertIsInstance(normalise_correction("a:b"), str)
        self.assertIsInstance(normalise_correction({"field": "a.b"}), str)


class TestIngestNormalisesEntries(unittest.TestCase):
    def test_ingest_rewrites_loose_checks_into_vocabulary(self):
        import json, os, tempfile
        from stages.verify_ingest import ingest
        with tempfile.TemporaryDirectory() as d:
            pend = os.path.join(d, ".pending_x.json")
            with open(pend, "w", encoding="utf-8") as f:
                json.dump([{"opportunity_id": 1, "verdict": "confirmed",
                            "reason": "ok",
                            "checks": ["issue:open", "timeline:无cross-referenced"]}],
                          f, ensure_ascii=False)
            ingest(pend, [1], log_dir=d, dry_run=False)
            line = json.loads(open(os.path.join(d, "2026-09-27.jsonl")
                                   if os.path.exists(os.path.join(d, "2026-09-27.jsonl"))
                                   else [p for p in os.listdir(d) if p.endswith(".jsonl")
                                         and p != "quarantine.jsonl"][0], encoding="utf-8").read().splitlines()[0])
            self.assertEqual(line["checks"], ["issue_state:open", "linked_pr:none"])


class TestCheckNormalisationSecondPass(unittest.TestCase):
    """回填历史日志时发现的最大残留在词表外：下划线/空格连接形式，以及把整句
    API 调用写进 checks。两者都能确定性解析。"""

    def test_underscore_joined_form(self):
        self.assertEqual(normalise_check("issue_state_open"), "issue_state:open")
        self.assertEqual(normalise_check("issue_state_closed"), "issue_state:closed")

    def test_negated_underscore_form_maps_to_none(self):
        for raw in ("timeline_no_linked_pr", "no_linked_pr", "timeline_no_xref_pr",
                    "no_wontfix_label", "labels_no_wontfix", "gap_desc_no_meta"):
            out = normalise_check(raw)
            self.assertTrue(out.endswith(":none") or ":none:" in out, f"{raw} -> {out}")

    def test_equals_separated_label_form(self):
        self.assertEqual(normalise_check("labels=question"), "issue_labels:question")
        self.assertEqual(normalise_check("label=bug"), "issue_labels:bug")

    def test_full_api_call_sentence(self):
        self.assertEqual(
            normalise_check("GET /repos/pressly/goose/issues/869 state=open"),
            "issue_state:open")

    def test_bare_issue_number_keeps_both_parts(self):
        out = normalise_check("issue#1247")
        self.assertIn("1247", out)

    def test_multi_fact_string_yields_none_for_each_negation(self):
        self.assertEqual(normalise_check("no wontfix/not-planned label"),
                         "issue_labels:none")

    def test_detail_prose_is_preserved_not_guessed(self):
        """无法可靠解析的长句原样保留——宁可留噪音，也不要猜错方向。"""
        raw = "experimental implementation exists (proposal #3264, cue exp writefs)"
        self.assertEqual(normalise_check(raw), raw)


class TestCheckValueNormalisation(unittest.TestCase):
    """键归并后，值仍是碎片：linked_pr 同时有 none / no_linked_pr / 0_xref /
    0_cross_ref_pr / False / no-linked-pr 六种同义写法。"""

    NONE_LIKE = ("none", "no_linked_pr", "0_xref", "0_cross_ref_pr", "false",
                 "no-linked-pr", "no_linked", "absent", "no", "[]", "miss",
                 "0", "no_xref", "no cross-referenced pr", "0_events", "clean")
    PRESENT_LIKE = ("present", "yes", "true", "found", "hit", "1", "有", "存在")

    def test_none_variants_collapse(self):
        for raw in self.NONE_LIKE:
            self.assertEqual(normalise_check(f"linked_pr:{raw}"), "linked_pr:none", raw)

    def test_present_variants_collapse(self):
        for raw in self.PRESENT_LIKE:
            self.assertEqual(normalise_check(f"linked_pr:{raw}"), "linked_pr:present", raw)

    def test_case_and_space_insensitive(self):
        self.assertEqual(normalise_check("linked_pr: No Linked PR "), "linked_pr:none")
        self.assertEqual(normalise_check("ISSUE_STATE:Closed"), "issue_state:closed")

    def test_state_values_preserved_verbatim(self):
        for v in ("open", "closed", "completed", "not_planned", "reopened"):
            self.assertEqual(normalise_check(f"issue_state:{v}"), f"issue_state:{v}")

    def test_http_codes_preserved(self):
        self.assertEqual(normalise_check("canonical_url:200"), "canonical_url:200")
        self.assertEqual(normalise_check("canonical_url:404"), "canonical_url:404")

    def test_label_name_preserved(self):
        self.assertEqual(normalise_check("issue_labels:question"), "issue_labels:question")

    def test_similar_prs_values(self):
        for raw in ("merged", "present", "unrelated"):
            self.assertEqual(normalise_check(f"similar_prs:{raw}"), f"similar_prs:{raw}")


class TestVocabularyAndAliasesStayInSync(unittest.TestCase):
    """每个词表键都必须有到自身的别名映射，否则 "<key>:<value>" 会落进
    joined 分支并丢掉 value（canonical_url:200 -> canonical_url:pass）。"""

    def test_every_vocab_key_maps_to_itself(self):
        for k in CHECK_VOCAB:
            self.assertEqual(_CHECK_ALIASES.get(k), k,
                             f"{k} 缺自身映射，会在冒号路径丢值")
