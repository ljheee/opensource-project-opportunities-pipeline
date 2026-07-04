# Smoke Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand `tests/test_analyze.py` with offline smoke tests for the pure helpers in `stages/analyze.py` and an evidence JSON contract test.

**Architecture:** Keep using the existing `unittest` framework and inline fixtures. No new dependencies or GitHub API calls.

**Tech Stack:** Python standard library `unittest`.

---

### Task 1: Add helper boundary tests

**Files:**
- Modify: `tests/test_analyze.py`

- [ ] **Step 1: Add tests for `_extract_keywords`**

```python
def test_empty_and_stop_words(self):
    self.assertEqual(analyze._extract_keywords(""), set())
    self.assertEqual(analyze._extract_keywords("this with from"), set())

def test_normal_keywords(self):
    self.assertEqual(analyze._extract_keywords("Fix memory allocation bug"), {"memory", "allocation"})
```

- [ ] **Step 2: Add tests for `_extract_quote_around_keyword`**

```python
def test_quote_not_found(self):
    self.assertEqual(analyze._extract_quote_around_keyword("hello world", "missing"), "")

def test_quote_found(self):
    q = analyze._extract_quote_around_keyword("we hit a production outage today", "production", 20)
    self.assertIn("production", q)
```

- [ ] **Step 3: Add tests for `_extract_prod_signal_quote`**

```python
def test_prod_signal_in_body(self):
    q, has = analyze._extract_prod_signal_quote("crash in production", [])
    self.assertTrue(has)
    self.assertIn("production", q)

def test_prod_signal_in_comment(self):
    q, has = analyze._extract_prod_signal_quote("", [{"body": "we use it in production"}])
    self.assertTrue(has)

def test_no_prod_signal(self):
    q, has = analyze._extract_prod_signal_quote("just a bug", [])
    self.assertFalse(has)
    self.assertEqual(q, "")
```

- [ ] **Step 4: Add tests for `_count_related_issues`**

```python
def test_no_related(self):
    issues = [{"title": "foo", "body": "bar"}]
    self.assertEqual(analyze._count_related_issues(issues, "unrelated", "text"), 0)

def test_related_by_keywords(self):
    issues = [{"title": "memory leak", "body": "alloc failure"}]
    self.assertGreaterEqual(analyze._count_related_issues(issues, "memory allocation", "bug"), 1)
```

- [ ] **Step 5: Add tests for `_find_related_paths`**

```python
def test_empty_paths(self):
    self.assertEqual(analyze._find_related_paths([], "foo"), [])

def test_keyword_match(self):
    paths = ["src/memory.go", "src/network.go"]
    self.assertEqual(analyze._find_related_paths(paths, "memory"), ["src/memory.go"])
```

- [ ] **Step 6: Add tests for `_has_stub`**

```python
def test_has_stub(self):
    self.assertTrue(analyze._has_stub(["src/raft.go"], "raft"))
    self.assertFalse(analyze._has_stub(["src/main.go"], "raft"))
```

- [ ] **Step 7: Add tests for `_find_approach_file`**

```python
def test_explicit_file(self):
    self.assertEqual(analyze._find_approach_file([], "bug", "see src/engine.go"), "src/engine.go")

def test_perf_fallback(self):
    paths = ["src/memory.go"]
    self.assertEqual(analyze._find_approach_file(paths, "slow memory", ""), "src/memory.go")
```

- [ ] **Step 8: Add tests for `_make_gap_desc`**

```python
def test_gap_desc_variants(self):
    self.assertIn("canonical implementation", analyze._make_gap_desc("feature_gap", "foo"))
    self.assertIn("security", analyze._make_gap_desc("security", "xss"))
    self.assertIn("performance", analyze._make_gap_desc("performance", "slow"))
    self.assertIn("reported", analyze._make_gap_desc("issue", "bug"))
```

- [ ] **Step 9: Add tests for `_make_why_hard`**

```python
def test_why_hard_concurrency(self):
    self.assertIn("concurrency", analyze._make_why_hard("issue", "race in mutex", "", False))

def test_why_hard_default(self):
    self.assertIn("unclear", analyze._make_why_hard("issue", "foo", "", False))
```

- [ ] **Step 10: Run helper tests**

Run: `python -m unittest tests.test_analyze -v`
Expected: PASS

---

### Task 2: Add evidence JSON contract test

**Files:**
- Modify: `tests/test_analyze.py`

- [ ] **Step 1: Add test that constructs opportunity evidence dicts**

```python
def test_evidence_json_contract(self):
    value_evidence = json.loads(json.dumps({
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 5,
        "issue_count": 1,
        "has_workaround": False,
        "prod_signal_quote": "",
        "has_prod_signal": False,
        "gap_desc": "gap",
    }))
    self.assertIsInstance(value_evidence["issue_reactions"], int)
    self.assertIsInstance(value_evidence["peer_impl_urls"], list)
    # similar for difficulty/urgency/maintainer evidence
```

- [ ] **Step 2: Run all tests**

Run: `python -m unittest tests.test_analyze -v`
Expected: PASS

---

### Task 3: Add structural helper tests

**Files:**
- Modify: `tests/test_analyze.py`

- [ ] **Step 1: Add tests for `get_tree_paths`, `get_root_dirs`, `get_key_files`**

```python
def test_tree_and_dirs(self):
    tree = {"tree": [{"path": "src/main.go"}, {"path": "README.md"}]}
    paths = analyze.get_tree_paths(tree)
    self.assertEqual(sorted(paths), ["README.md", "src/main.go"])
    self.assertEqual(analyze.get_root_dirs(paths), ["src"])
```

- [ ] **Step 2: Add tests for `parse_owner_repo` and `decode_readme`**

```python
def test_parse_and_readme(self):
    self.assertEqual(analyze.parse_owner_repo("https://github.com/foo/bar"), ("foo", "bar"))
    self.assertEqual(analyze.parse_owner_repo(""), (None, None))
```

- [ ] **Step 3: Run all tests**

Run: `python -m unittest tests.test_analyze -v`
Expected: PASS

---

### Task 4: Final review and commit

- [ ] **Step 1: Review test file for readability and coverage**
- [ ] **Step 2: Run full test suite**
- [ ] **Step 3: Commit**

```bash
git add tests/test_analyze.py docs/superpowers/specs/2026-07-04-smoke-tests-design.md docs/superpowers/plans/2026-07-04-smoke-tests-plan.md
git commit -m "test: expand smoke tests for analyze evidence helpers"
```
