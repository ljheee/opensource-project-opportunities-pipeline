#!/usr/bin/env python3
"""Apply Stage 4 v2 batch judgment for tasks 1170, 1171 on 2026-08-29."""
import json
import sqlite3

DB = "data/pipeline.db"
NOW = "2026-08-29T22:00:00+00:00"

conn = sqlite3.connect(DB)
c = conn.cursor()


def up(oid, st, title, desc, hint, ve, de, ue, me):
    c.execute("""UPDATE opportunities
       SET status='open', source_type=?, title=?, description=?, impl_hint=?,
           value_evidence=?, difficulty_evidence=?, urgency_evidence=?, maintainer_evidence=?,
           value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
       WHERE id=?""", (st, title, desc, hint, ve, de, ue, me, oid))


def delete(oid):
    c.execute("DELETE FROM opportunities WHERE id=?", (oid,))


# ===== 2862: nats.net performance - Ordered consumer performance =====
ve = json.dumps({
    "canonical_impl_url": "https://github.com/nats-io/nats.go/blob/main/jetstream/ordered.go",
    "canonical_impl_loc": 0,
    "peer_impl_urls": ["https://github.com/nats-io/nats.rs/blob/main/async-nats/src/jetstream/ordered.rs"],
    "issue_reactions": 1,
    "issue_count": 38,
    "has_workaround": False,
    "prod_signal_quote": "Ordered consumer performance is our gold standard benchmark for consumers. Test and improve ordered consumer performance.",
    "has_prod_signal": True,
    "gap_desc": "Project owners seek improved ordered consumer performance benchmarks; C# .NET implementation lags Go canonical baseline"
})
de = json.dumps({
    "canonical_impl_url": "https://github.com/nats-io/nats.go/blob/main/jetstream/ordered.go",
    "canonical_impl_loc": 0,
    "why_hard": "Requires deep knowledge of NATS JetStream protocol internals, receive buffer management, and .NET async I/O tuning"
})
ue = json.dumps({"has_prod_signal": True, "has_workaround": False})
me = json.dumps({"similar_prs": [], "welcome_labels": [], "maintainer_responses": []})
up(2862, "performance",
   "Improve ordered consumer performance to match Go baseline",
   "Project owners want the C# .NET ordered consumer performance to match the Go canonical implementation, which is their gold-standard benchmark.",
   "Profile hot paths in NatsJSOrderedConsumer; reduce allocations in the receive buffer path; consider Span/MemoryPool reuse.",
   ve, de, ue, me)

# 7711: feature_gap Makefile - DELETE (blacklisted meta/build file)
delete(7711)
# 7712: feature_gap encoders - DELETE (nats.net has JSON+protobuf serializers)
delete(7712)
# 7713: feature_gap internal - DELETE (nats.net has src/NATS.Client.Core/Internal/)
delete(7713)
# 7714: security "Real-World Examples" - DELETE (duplicate of verified 2860 issue:568)
delete(7714)
# 7715: compatibility DuplicateWindow - DELETE (duplicate of open 5311 issue:736)
delete(7715)

# 7716: performance throttling object store reads
ve = json.dumps({
    "canonical_impl_url": "https://github.com/nats-io/nats.go/blob/main/jetstream/object_store.go",
    "canonical_impl_loc": 0,
    "peer_impl_urls": ["https://github.com/nats-io/nats.rs/blob/main/async-nats/src/object_store.rs"],
    "issue_reactions": 2,
    "issue_count": 39,
    "has_workaround": False,
    "prod_signal_quote": "we want to stream large files from object store directly to an HTTP endpoint. We know our reads from NATS server may be faster than the network egress",
    "has_prod_signal": True,
    "gap_desc": "Object store reads lack throttling options (chunkSize, maxBytesPerSecond, delay), causing slow consumer events when reads outpace uploads"
})
de = json.dumps({
    "canonical_impl_url": "https://github.com/nats-io/nats.go/blob/main/jetstream/object_store.go",
    "canonical_impl_loc": 0,
    "why_hard": "Medium: requires async rate-limiting primitives in Store.GetAsync; must integrate with IAsyncEnumerable<byte[]> streaming surface"
})
ue = json.dumps({"has_prod_signal": True, "has_workaround": False})
me = json.dumps({"similar_prs": [], "welcome_labels": [], "maintainer_responses": []})
up(7716, "performance",
   "Add throttling options for object store reads (chunkSize / maxBytesPerSecond / delay)",
   "Feature request to add throttling controls to NATS Object Store GetAsync so streaming large files to HTTP endpoints does not trigger slow-consumer events.",
   "Add Config.ChunkSize / MaxBytesPerSecond / Delay fields; throttle the per-message reads in GetAsync accordingly; document the use case.",
   ve, de, ue, me)

# 7718: issue JsonWriterOptions
ve = json.dumps({
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "peer_impl_urls": [],
    "issue_reactions": 1,
    "issue_count": 29,
    "has_workaround": False,
    "prod_signal_quote": "Would be nice to enable using our own JavaScriptEncoder while reusing the logic of the serialiser class. Eg. the unicode escaping in messages at the moment is quite tough on the eyes when inspecting the raw values of the keys via NATS CLI",
    "has_prod_signal": False,
    "gap_desc": "NatsJsonSerializer<T> does not accept JsonWriterOptions, preventing users from supplying a custom JavaScriptEncoder"
})
de = json.dumps({
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "why_hard": "Easy: thread JsonWriterOptions through NatsJsonSerializer<T> constructor and propagate to Utf8JsonWriter"
})
ue = json.dumps({"has_prod_signal": False, "has_workaround": False})
me = json.dumps({"similar_prs": [], "welcome_labels": [], "maintainer_responses": [{"author_association": "NONE", "body_quote": "I can contribute if the idea is approved", "issue_number": 1219}]})
up(7718, "issue",
   "Add JsonWriterOptions parameter to NatsJsonSerializer<T> constructor",
   "User requests ability to pass JsonWriterOptions (especially JavaScriptEncoder) into NatsJsonSerializer<T> for friendlier raw-key inspection via NATS CLI.",
   "Add JsonWriterOptions overload to NatsJsonSerializer<T>; default to existing behavior; plumb through to Utf8JsonWriter.",
   ve, de, ue, me)

# 7719: security "GetKeysAsync hangs" - reclassify to issue (bug)
ve = json.dumps({
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "peer_impl_urls": [],
    "issue_reactions": 1,
    "issue_count": 40,
    "has_workaround": True,
    "prod_signal_quote": "GetKeysAsync(IEnumerable<string> filters, ...) hangs indefinitely when the filter pattern matches zero keys in the bucket, even though the bucket contains other keys",
    "has_prod_signal": True,
    "gap_desc": "INatsKVStore.GetKeysAsync hangs forever when no keys match the supplied filter pattern; client-side filtering was the workaround"
})
de = json.dumps({
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "why_hard": "Medium: requires tracing the KV watch/iterator cancellation path when the underlying stream yields no matches"
})
ue = json.dumps({"has_prod_signal": True, "has_workaround": True})
me = json.dumps({"similar_prs": [], "welcome_labels": [], "maintainer_responses": []})
up(7719, "issue",
   "Fix: GetKeysAsync hangs indefinitely when no keys match the filter pattern",
   "Bug: INatsKVStore.GetKeysAsync(IEnumerable<string> filters) hangs when the filter pattern matches zero keys, even though other keys exist in the bucket.",
   "Locate the watcher teardown path for zero-match filters; ensure the enumerator completes (or surfaces an empty result) instead of blocking.",
   ve, de, ue, me)

# 7720: performance "INats(Js)Msg implement INatsJsMsg" - DELETE (duplicate of verified 5314 issue:1027)
delete(7720)

# ===== Task 1171: nats-io/nats.rs (Rust) =====

# 7043: security v0.45.0 CVE patch
ve = json.dumps({
    "cve_id": None,
    "vulnerable_dep": "async-nats 0.45.0",
    "fixed_in_dep": "0.45.x (security patch request)",
    "canonical_fixed": True,
    "peer_fixed": [{"lang": "Go", "fixed": True}],
    "affected_file": "async-nats/Cargo.toml",
    "affected_api": "async-nats 0.45.0 release artifact",
    "attack_surface": "Security issue in 0.45.0 already fixed in 0.47.0, but 0.47.0 requires Rust 1.88; users on Rust 1.75 (yocto scarthgap LTS) cannot upgrade"
})
de = json.dumps({
    "canonical_impl_url": "https://github.com/nats-io/nats.rs/blob/main/async-nats/Cargo.toml",
    "canonical_impl_loc": 0,
    "why_hard": "Medium: requires backporting the security fix from 0.47.0 onto the 0.45.x branch while maintaining Rust 1.75 MSRV compatibility"
})
ue = json.dumps({"cve_id": None, "has_prod_signal": True, "has_workaround": False})
me = json.dumps({"similar_prs": [], "welcome_labels": [], "maintainer_responses": []})
up(7043, "security",
   "Backport security fix to async-nats 0.45.0 (Rust 1.75 MSRV)",
   "async-nats 0.45.0 has a security issue already fixed in 0.47.0, but 0.47.0 requires Rust 1.88. Users on yocto scarthgap LTS (max Rust 1.75) need a 0.45.x patch release.",
   "Identify the CVE fix in 0.47.0; backport minimal patches onto a 0.45.x release branch; verify MSRV stays at 1.75.",
   ve, de, ue, me)

# 7044: issue "Break apart request/response"
ve = json.dumps({
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "peer_impl_urls": ["https://github.com/nats-io/nats.go/blob/main/nats.go"],
    "issue_reactions": 1,
    "issue_count": 23,
    "has_workaround": False,
    "prod_signal_quote": "In some cases, you may want to shoot off a bunch of requests and defer processing the responses til later. Introduce a Response<T = Message> type",
    "has_prod_signal": False,
    "gap_desc": "Currently request().await? blocks until response is received; users want to separate the send completion from the response handling"
})
de = json.dumps({
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "why_hard": "Medium: requires redesigning Client::request to return a future that resolves to a response future, balancing ergonomics with type complexity"
})
ue = json.dumps({"has_prod_signal": False, "has_workaround": False})
me = json.dumps({"similar_prs": [], "welcome_labels": [], "maintainer_responses": []})
up(7044, "issue",
   "Decouple request send and response receive (Response<T> as future of future)",
   "Feature request: allow Client::request to return a Response<T> that decouples the send-completion future from the response future, enabling deferred response processing.",
   "Introduce Response<T = Message> with IntoFuture impl; have Client::request return one; document the two-stage await pattern.",
   ve, de, ue, me)

# 7045: issue "Push Consumer Config default"
ve = json.dumps({
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "peer_impl_urls": [],
    "issue_reactions": 0,
    "issue_count": 24,
    "has_workaround": False,
    "prod_signal_quote": "The deliver_subject field is required in order for a push consumer to work properly, at least mine was not working properly without it. The issue is that pull::Config implements Default and #[serde(default)] for the deliver_subject field",
    "has_prod_signal": False,
    "gap_desc": "push::Config default does not warn/error on missing deliver_subject; users can produce broken configurations silently"
})
de = json.dumps({
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "why_hard": "Easy: add a Debug/Default/serde check, or a builder-time validation that errors on empty deliver_subject for push consumers"
})
ue = json.dumps({"has_prod_signal": False, "has_workaround": False})
me = json.dumps({"similar_prs": [], "welcome_labels": [], "maintainer_responses": []})
up(7045, "issue",
   "Warn or error when push::Config.deliver_subject is empty",
   "Bug-prone default: push::Config implements Default with empty deliver_subject, leading to silent misconfiguration. Add a runtime check or remove the default.",
   "Implement a build-time validation step on Config::build() that errors when deliver_subject is None for push consumers.",
   ve, de, ue, me)

# 7701: feature_gap Makefile - DELETE (blacklisted)
delete(7701)
# 7702: feature_gap bench - DELETE (nats.rs has async-nats/benches and nats/benches)
delete(7702)

# 7703: feature_gap encoders - KEEP, real gap (no protobuf in nats.rs)
ve = json.dumps({
    "canonical_impl_url": "https://github.com/nats-io/nats.go/tree/main/encoders/protobuf",
    "canonical_impl_loc": 0,
    "peer_impl_urls": ["https://github.com/nats-io/nats.go/tree/main/encoders/builtin"],
    "target_has_stub": False,
    "target_related_files": [],
    "feature_desc": "Protobuf encoder for NATS message payloads",
    "gap_desc": "nats.rs has no protobuf encoder at all; only the built-in JSON default",
    "feature_verification": {
        "searched_terms": ["protobuf", "protobuf encoder", "prost", "prost-derive", "prost::Message"],
        "search_scope": "repo directory tree + GitHub code search API (q=protobuf repo:nats-io/nats.rs, total=0)",
        "result": "no-hit",
        "checked_at": "2026-08-29"
    }
})
de = json.dumps({
    "canonical_impl_url": "https://github.com/nats-io/nats.go/tree/main/encoders/protobuf",
    "canonical_impl_loc": 0,
    "why_hard": "Medium: requires integrating prost (or similar) as an optional dependency, designing a codec trait analogous to nats.go's Encodable, and supporting both pub and sub paths"
})
ue = json.dumps({"has_prod_signal": False, "has_workaround": True})
me = json.dumps({"similar_prs": [], "welcome_labels": [], "maintainer_responses": []})
up(7703, "feature_gap",
   "Add Protobuf encoder (port from nats.go encoders/protobuf)",
   "nats.rs ships only a JSON default codec. nats.go has a dedicated encoders/protobuf package; users on Rust have no equivalent, so they hand-roll serde + bytes wrappers.",
   "Add an `async_nats::protobuf` module gated on a 'protobuf' cargo feature; implement encode/decode via prost::Message; expose a Subscriber/Publisher-friendly codec trait.",
   ve, de, ue, me)

# 7704: feature_gap internal - DELETE (Rust doesn't use Go's internal/ convention)
delete(7704)
# 7705: security "1.0.0 release planning" - DELETE (meta discussion/RFC)
delete(7705)
# 7706: security "KV Watch iterator hangs" - DELETE (duplicate of open 7041 issue:795)
delete(7706)

# 7707: issue "runtime independent"
ve = json.dumps({
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "peer_impl_urls": [],
    "issue_reactions": 3,
    "issue_count": 26,
    "has_workaround": False,
    "prod_signal_quote": "Hey. I think we should make async-nats independent from tokio. While tokio remains the standard in the async Rust ecosystem, stable Rust has now standardized wasip2, and we can handle almost all IO with the second preview",
    "has_prod_signal": False,
    "gap_desc": "async-nats hard-depends on tokio, blocking wasip2 users; tokio's lack of wasip2 support is the blocker"
})
de = json.dumps({
    "canonical_impl_url": "",
    "canonical_impl_loc": 0,
    "why_hard": "Hard: requires abstracting I/O traits over runtimes (e.g., futures-io / async-io), significant refactor of the connector and stream modules"
})
ue = json.dumps({"has_prod_signal": False, "has_workaround": False})
me = json.dumps({"similar_prs": [], "welcome_labels": [], "maintainer_responses": []})
up(7707, "issue",
   "Decouple async-nats from tokio to enable wasip2 and alternative runtimes",
   "Feature request: async-nats should be runtime-agnostic; currently tokio-locked, blocking wasip2 users (no upstream PR in mio merged since Nov).",
   "Introduce an I/O abstraction (e.g., futures-io or smol-style traits) inside the connector module; gate tokio behind a feature flag.",
   ve, de, ue, me)

# Mark tasks done
c.execute("UPDATE tasks SET status='done', finished_at=? WHERE id=1170", (NOW,))
c.execute("UPDATE tasks SET status='done', finished_at=? WHERE id=1171", (NOW,))
# Mark projects active
c.execute("UPDATE projects SET status='active' WHERE id='nats-io/nats.net' AND status='analyzing'")
c.execute("UPDATE projects SET status='active' WHERE id='nats-io/nats.rs' AND status='analyzing'")

conn.commit()

# Report
print("=== Opportunities after ===")
c.execute("SELECT id, status, source_type, title FROM opportunities WHERE task_id IN (1170,1171) ORDER BY task_id, id")
for row in c.fetchall():
    print(row)
print("=== Tasks ===")
c.execute("SELECT id, status, finished_at FROM tasks WHERE id IN (1170,1171)")
for row in c.fetchall():
    print(row)
print("=== Projects ===")
c.execute("SELECT id, status FROM projects WHERE id IN ('nats-io/nats.net','nats-io/nats.rs')")
for row in c.fetchall():
    print(row)
conn.close()
