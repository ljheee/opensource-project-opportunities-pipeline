# Smoke Tests for stages/analyze.py

## Goal
Add fast, offline smoke tests for the evidence helpers in `stages/analyze.py` so that regressions in boundary handling, evidence JSON shape, and helper interactions are caught before a real pipeline run.

## Scope
Pure helpers only — no GitHub API calls. The tests mock inputs in-memory.

Covered helpers:
- `_extract_keywords`
- `_extract_quote_around_keyword`
- `_extract_prod_signal_quote`
- `_count_related_issues`
- `_find_related_paths`
- `_has_stub`
- `_find_approach_file`
- `_make_gap_desc`
- `_make_why_hard`
- `classify_issue` (existing + perf/compatibility)
- `get_tree_paths`
- `get_root_dirs`
- `get_key_files`
- `parse_owner_repo`
- `decode_readme`

Also add an "evidence JSON contract" test that builds the dicts assembled in `analyze_project` and asserts required fields and types in `value_evidence`, `difficulty_evidence`, `urgency_evidence`, and `maintainer_evidence`.

## Approach
Use the existing `unittest` framework in `tests/test_analyze.py` with inline fixtures. No new dependencies. Run with:

```bash
python -m unittest tests.test_analyze
```

## Success Criteria
- All tests pass.
- Each helper has at least one boundary case (empty input, `None`, empty list).
- Evidence contract test fails if a required field is removed or changes type.
