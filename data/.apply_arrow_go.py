#!/usr/bin/env python3
"""Stage 4 v2 batch judgment for tasks 1177/1188/1189 on date 2026-08-30."""
import sqlite3, json, sys

DB = 'data/pipeline.db'

conn = sqlite3.connect(DB)
cur = conn.cursor()

def delete_opp(opp_id, why):
    cur.execute("DELETE FROM opportunities WHERE id = ?", (opp_id,))
    print(f"DELETE {opp_id}: {why}")

def promote(opp_id, *, source_type, title, description, impl_hint,
            value_evidence, difficulty_evidence, urgency_evidence, maintainer_evidence):
    cur.execute("""
        UPDATE opportunities SET
            status='open',
            source_type=?,
            title=?,
            description=?,
            impl_hint=?,
            value_evidence=?,
            difficulty_evidence=?,
            urgency_evidence=?,
            maintainer_evidence=?,
            value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
        WHERE id=?
    """, (source_type, title, description, impl_hint,
          json.dumps(value_evidence), json.dumps(difficulty_evidence),
          json.dumps(urgency_evidence), json.dumps(maintainer_evidence),
          opp_id))
    print(f"PROMOTE {opp_id} -> open ({source_type}): {title}")

# ============================================================
# PROJECT 1: apache/arrow-go (task 1189)
# ============================================================

# 4 feature_gap drafts: c_glib, cpp, matlab, python are LANGUAGE BINDING
# modules in the C++ Apache Arrow canonical repo. Go bindings ARE arrow-go;
# "missing cpp module" is nonsensical.
for oid in (7779, 7780, 7781, 7782):
    delete_opp(oid, "nonsensical language-binding gap vs C++ canonical")

# 7785 — meta RFC/discussion (ALP encoding feedback invitation)
delete_opp(7785, "meta-discussion RFC invitation, gap_desc contains 'survey/RFC/designing' markers")

# 2998 — perf, custom allocator in ReaderProperties.GetStream
promote(2998,
    source_type='performance',
    title='[Go][Parquet] Use custom allocator in ReaderProperties.GetStream',
    description="ReaderProperties.GetStream in parquet/reader_properties.go#L80 unconditionally `make()`s ~2GB for a 2GB S3 file (~33% of total allocations). The struct already has an `Allocator` field; thread it through the buffer creation in GetStream so callers can plug in a custom allocator.",
    impl_hint="Replace the unconditional `make([]byte, n)` with `props.Allocator.Allocate(n)` (or a borrowed buffer when allocator is nil). Mirror the pattern from PR #485 which introduced allocator usage in `serializedPageReader`.",
    value_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 1,
        "issue_count": 24,
        "has_workaround": False,
        "prod_signal_quote": "We're testing reading parquet files from S3 ... 2GB file ... the `make` call in reader_properties.go#L80 allocates about 2GB of data, which is about a third of the total allocations that our test that reads the whole file does.",
        "has_prod_signal": True,
        "gap_desc": "parquet/reader_properties.go#L80 in GetStream unconditionally `make()`s the read buffer rather than using the existing ReaderProperties.Allocator, wasting ~30% of allocations for large S3 reads"
    },
    difficulty_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: requires touching the low-level read path and ensuring allocator-aware allocation works for all readers (file/S3/buffered)",
        "target_approach_file": "parquet/reader_properties.go"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    maintainer_evidence={
        "similar_prs": [
            {"number": 880, "title": "feat(parquet): opt-in streaming reads for large data pages", "merged": True, "url": "https://github.com/apache/arrow-go/pull/880", "age_days": 59, "maintainer_comment": ""},
            {"number": 485, "title": "feat(parquet): utilize memory allocator in `serializedPageReader`", "merged": True, "url": "https://github.com/apache/arrow-go/pull/485", "age_days": 368, "maintainer_comment": ""}
        ],
        "maintainer_responses": [
            {"body_quote": "Seems like a reasonable approach. Would you be up for making a PR for this?"},
            {"body_quote": "Maybe using io.ReadFull also needs to call r.Read multiple times when reading from S3 (We are also reading files from S3)."}
        ],
        "welcome_labels": []
    })

# 2999 — issue, schema inference on RecordFromJSON/TableFromJSON
promote(2999,
    source_type='issue',
    title='[Go] Schema inference on RecordFromJSON and TableFromJSON',
    description="`RecordFromJSON` and `TableFromJSON` in the Go implementation require an explicit `arrow.Schema`, forcing users to declare types ahead of time. The Go CSV reader already supports inference via `csv.NewInferringReader`; mirror that pattern so JSON readers can infer types from the first row.",
    impl_hint="Mirror the type-inference pattern already implemented for CSV in `arrow/csv/reader.go` (NewInferringReader). Add an `Inferring` option or a parallel constructor that scans the first N rows of the JSON to determine the Schema, then re-reads with that schema.",
    value_evidence={
        "canonical_impl_url": "https://github.com/apache/arrow-go/blob/main/arrow/csv/reader.go#L75",
        "canonical_impl_loc": 75,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 24,
        "has_workaround": True,
        "prod_signal_quote": "I am interested in support for schema inference in the `RecordFromJSON` and `TableFromJSON` functions, as these currently require an `arrow.Schema` up front.",
        "has_prod_signal": True,
        "gap_desc": "JSON readers in arrow-go force users to declare an arrow.Schema upfront, while CSV reader (same repo) already supports inference — parity is missing"
    },
    difficulty_evidence={
        "canonical_impl_url": "https://github.com/apache/arrow-go/blob/main/arrow/csv/reader.go#L75",
        "canonical_impl_loc": 75,
        "why_hard": "Hard because: schema inference requires JSON-aware type heuristics; must handle nested types and nulls",
        "target_approach_file": "arrow/internal/arrjson"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": True},
    maintainer_evidence={
        "similar_prs": [],
        "maintainer_responses": [
            {"body_quote": "Hi @agchang, thanks for opening this issue. I think this feature very well may make sense to implement, and we would welcome your contribution if you decide to do so!"}
        ],
        "welcome_labels": []
    })

# 3000 — perf, Golang arenas
promote(3000,
    source_type='performance',
    title='[Go] Implement Usage of Golang arenas (go1.20+)',
    description="Go 1.20+ added an experimental `arena` package that can dramatically reduce GC pressure by manually managing allocations in bulk. arrow-go would benefit significantly — arrays, record batches, and parquet pages all allocate many small buffers per call.",
    impl_hint="Add an opt-in arena-aware allocator alongside the existing `Allocator` interface in `arrow/memory`. Wrap Record/Array builders so they can optionally allocate from an arena. Provide benchmarks using `go test -bench -benchmem` (per maintainer guidance) to validate gains.",
    value_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 23,
        "has_workaround": False,
        "prod_signal_quote": "Golang v1.20 has added an experimental `arenas` package, which allows more 'manual' memory allocation and could be potentially useful for the golang arrow library.",
        "has_prod_signal": True,
        "gap_desc": "arrow-go's memory allocator predates Go 1.20 arenas and doesn't expose an arena-based fast path; heavy workloads allocate many small buffers per record"
    },
    difficulty_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: arenas are experimental and require careful handling of escape analysis; touchpoint spans the entire memory package",
        "target_approach_file": "arrow/memory"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    maintainer_evidence={
        "similar_prs": [],
        "maintainer_responses": [
            {"body_quote": "I think it's a great idea to try using an arena. To my knowledge there hasn't been any attempts yet, and I know that I've gotten at least one question about them, but that's all the interest I've seen"},
            {"body_quote": "there are benchmarks in the package that can be run via `go test -bench -benchmem` ... at a few different levels including in the compute package. Those should be sufficient to see differences"}
        ],
        "welcome_labels": []
    })

# 7783 — perf, Parquet from struct slice
promote(7783,
    source_type='performance',
    title='[Go][Parquet] Writing a Parquet file from a slice of structs',
    description="There is no efficient path in arrow-go for writing a parquet file given a slice of user-defined Go structs. `parquet.NewSchemaFromStruct` only helps derive a schema; users still must hand-convert each struct to an `array.Struct`/Record. This is one of the most common Go-to-parquet use cases.",
    impl_hint="Add a helper such as `parquet.WriteStructSlice[T any](w, slice)` that uses reflection to derive the parquet schema from the struct tags and writes records efficiently. Internally build a single Record from the slice rather than per-row.",
    value_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 2,
        "issue_count": 24,
        "has_workaround": True,
        "prod_signal_quote": "I'm hoping to get suggestions on the best way to use the library to write a Parquet file given a slice of structs (Golang structs instead of Arrow's array.Struct). The `parquet.NewSchemaFromStruct()` function looks like a useful start.",
        "has_prod_signal": True,
        "gap_desc": "arrow-go lacks an efficient struct-slice to parquet write path; users must manually convert to Arrow arrays, which is the dominant Go-parquet use case"
    },
    difficulty_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: requires reflection-based conversion of arbitrary Go structs to Arrow arrays while respecting parquet schema tags and nullability",
        "target_approach_file": "parquet/file"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": True},
    maintainer_evidence={
        "similar_prs": [],
        "maintainer_responses": [
            {"body_quote": "You're completely right, there isn't currently a good / efficient way to convert a slice of structs to an arrow record / struct array."},
            {"body_quote": "the `file` package is intended to be a 'general' parquet writer for use even if arrow is not used for the input data."}
        ],
        "welcome_labels": []
    })

# 7788 — perf, RecordFromJSON hangs
promote(7788,
    source_type='performance',
    title='[Go] array.RecordFromJSON() hangs on large JSON files',
    description="`array.RecordFromJSON()` either blocks indefinitely or processes excessively long when fed a ~200MB JSON file. The maintainer could not reproduce with random data, suggesting the bug is input-dependent (likely pathological schema or large-string columns).",
    impl_hint="Profile with `pprof` on a reproducer. Likely culprits: unbounded buffering, quadratic loops in type-dispatch, or large-string allocation. Add an integration test that streams a ~200MB JSON file with a realistic schema (e.g., one with large strings or nested lists).",
    value_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 24,
        "has_workaround": False,
        "prod_signal_quote": "When I attempt to use the array.RecordFromJSON() method to read a relatively large JSON file (approximately 200MB in size), the method does not return for a significant amount of time.",
        "has_prod_signal": True,
        "gap_desc": "RecordFromJSON exhibits near-infinite runtime on ~200MB JSON inputs (input-dependent hang), no clear workaround"
    },
    difficulty_evidence={
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: input-dependent; reproduce requires a pathological 200MB JSON file; root cause may be in string/list handling or memory allocator",
        "target_approach_file": "arrow/internal/arrjson"
    },
    urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    maintainer_evidence={
        "similar_prs": [],
        "maintainer_responses": [
            {"body_quote": "I'll take a look at this sometime this week."},
            {"body_quote": "Would you be able to provide the actual data file that causes the problem? I created a 200MB JSON file with random values using the format schema you provided and then ran the code you provided to read it."}
        ],
        "welcome_labels": []
    })

conn.commit()
conn.close()
print("apache/arrow-go batch complete")