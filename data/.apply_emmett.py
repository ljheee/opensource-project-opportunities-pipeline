#!/usr/bin/env python3
"""Apply emmett (task 1521) draft judgments."""
import json
import sqlite3
from pathlib import Path

DB = Path("/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db")

con = sqlite3.connect(DB)
cur = con.cursor()

def upd(opp_id, source_type, title, description, impl_hint,
        value_evidence, difficulty_evidence, urgency_evidence, maintainer_evidence):
    cur.execute(
        """UPDATE opportunities
           SET status='open', source_type=?, title=?, description=?, impl_hint=?,
               value_evidence=?, difficulty_evidence=?, urgency_evidence=?, maintainer_evidence=?,
               value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
           WHERE id=?""",
        (source_type, title, description, impl_hint,
         json.dumps(value_evidence), json.dumps(difficulty_evidence),
         json.dumps(urgency_evidence), json.dumps(maintainer_evidence), opp_id),
    )

# 4508 — Supabase compatibility (issue 93). Soft ask, but real integration work.
upd(
    4508,
    "compatibility",
    "Add first-class Supabase adapter + tutorial for Emmett",
    "Document and verify that Emmett runs on Supabase Postgres (and Supabase Realtime where relevant), and provide a step-by-step tutorial covering connection string format, prepared statements, and event-store schema migrations.",
    "Spin up an `emmett-supabase` adapter that wraps the existing postgres adapter and uses the Supabase connection string template; add a docs page under `docs/tutorials/supabase.md` plus a runnable sample under `samples/supabase/`.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 1,
        "issue_count": 6,
        "has_workaround": False,
        "prod_signal_quote": "",
        "has_prod_signal": False,
        "gap_desc": "Emmett has no documented Supabase setup path; users have to discover connection-string / SSL settings by trial",
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: needs verification of SSL modes, prepared-statement compatibility, and a tested migration path; mostly low risk.",
    },
    {"cve_id": None, "has_prod_signal": False, "has_workaround": False},
    {"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
)

# 8652 — ERR_MODULE_NOT_FOUND bug (issue 384)
upd(
    8652,
    "compatibility",
    "Fix @event-driven-io/emmett-testcontainers ERR_MODULE_NOT_FOUND when only Postgres helper is used",
    "When a user installs only the Postgres testing helper from `@event-driven-io/emmett-testcontainers`, the package crashes with `ERR_MODULE_NOT_FOUND` for `@eventstore/db-client`. The package depends on `@eventstore/db-client` but does not declare it as a dependency, so it is missing when installed in isolation.",
    "Either declare `@eventstore/db-client` as a regular dependency, or split the EventStore helper out of the testcontainers package (or lazy-require it) so the Postgres-only path does not pull it. Reproduction: `npm i -D @event-driven-io/emmett-testcontainers @event-driven-io/emmett-postgresql` then start a Postgres container in v22 ESM.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 19,
        "has_workaround": True,
        "prod_signal_quote": "@event-driven-io/emmett-testcontainers crashes with ERR_MODULE_NOT_FOUND when only using the Postgres helper - @eventstore/db-client isn't declared as a dependency anywhere",
        "has_prod_signal": True,
        "gap_desc": "Missing transitive dependency declaration in @event-driven-io/emmett-testcontainers breaks Postgres-only installs",
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: requires deciding between declaring an extra dep vs splitting the helper; affects package surface.",
        "target_approach_file": "packages/emmett-testcontainers/package.json",
    },
    {"cve_id": None, "has_prod_signal": True, "has_workaround": True},
    {"similar_prs": [], "maintainer_responses": [{"body_quote": "@Powerworks which version are you using 0.42.x?", "issue_number": 384}], "welcome_labels": []},
)

# 8654 — Vercel compatibility (issue 94). 0 reactions, no maintainer activity beyond a question. Low value, DELETE.
cur.execute("DELETE FROM opportunities WHERE id=8654")

# 8655 — snapshot testing (issue 21). Maintainer pointed at Node native test runner; useful pointer but low value as standalone opportunity. DELETE.
cur.execute("DELETE FROM opportunities WHERE id=8655")

# 4512 — StreamCategory on EventStore (issue 146). Design discussion but maintainer explicitly open.
upd(
    4512,
    "issue",
    "Add generic `StreamCategory` (and rename to `StreamName`) to the global EventStore interface",
    "Allow the EventStore interface to take a generic `StreamCategory extends string = string` (and similarly `StreamName extends string = string`) so that ES implementations can be more strongly typed while defaulting to plain string.",
    "In `packages/emmett/src/eventStore/EventStore.ts`, parameterize the interface with `<StreamCategory extends string = string, StreamName extends string = string>`. Backward compatible by defaulting to string. Add a small Mongo impl example.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 7,
        "has_workaround": False,
        "prod_signal_quote": "Maybe StreamName could also be a generic along with StreamType that defaults to string but could be overrided by the person creating to ES impl.",
        "has_prod_signal": False,
        "gap_desc": "EventStore interface is monomorphic on stream name; downstream impls cannot tighten category types without forking",
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: surface API; generic defaulting and downstream typings need a careful rollout.",
        "target_approach_file": "packages/emmett/src/eventStore/EventStore.ts",
    },
    {"cve_id": None, "has_prod_signal": False, "has_workaround": False},
    {"similar_prs": [], "maintainer_responses": [
        {"body_quote": "Would be useful to get TS inference for when attempting to use the event store functions if you already have a set list of categories.", "issue_number": 146},
        {"body_quote": "Open to whatever naming convetions ESDB uses or whatever is most common", "issue_number": 146},
    ], "welcome_labels": []},
)

# 4515 — MongoDB ObjectId strings stored as ObjectId (issue 149)
upd(
    4515,
    "issue",
    "MongoDB EventStore: store strings that look like ObjectId as ObjectId",
    "MongoDB EventStore serializes an ObjectId-typed ID as a plain string, which makes equality queries against actual ObjectId fields return empty result sets. Add an ObjectId-detection helper and use it on read and write paths.",
    "In the MongoDB event-store adapter, add a small `coerceToObjectId(value)` that recognizes 24-hex strings and use it both when serializing events and when building equality filters in projections. Add a test covering the round-trip and the projection-filter case.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 15,
        "has_workaround": True,
        "prod_signal_quote": "MongoDB has this fun quirk that ObjectIds are not comparable to string types when attempting aggregations.",
        "has_prod_signal": False,
        "gap_desc": "ObjectId/string mismatch silently breaks Mongo projection filters and aggregation joins in EventStore",
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: type-detection must be conservative (avoid false positives); affects both write and read paths.",
        "target_approach_file": "packages/emmett-mongodb/src/",
    },
    {"cve_id": None, "has_prod_signal": False, "has_workaround": True},
    {"similar_prs": [], "maintainer_responses": [
        {"body_quote": "@alex-laycalvert sounds fair, but it'd be worth researching how others are handling it. The challenge that we may be facing are false positives.", "issue_number": 149}
    ], "welcome_labels": []},
)

# 8650 — Event store usage without command handler documentation (issue 284). Real doc ask, maintainer invites PR.
upd(
    8650,
    "issue",
    "Document using the event store without the command handler",
    "Add an API-reference and tutorial page showing how to use Emmett's event store independently of the command-handler layer (raw appendToStream / readStream). The maintainer explicitly invited PRs for this gap.",
    "Write `docs/eventStore/standalone.md` walking through appendToStream, readStream, and a minimal projection. Cross-link from `docs/README.md`. Include a small code sample under `samples/standalone-event-store/`.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 12,
        "has_workaround": False,
        "prod_signal_quote": "I've been using Emmett for a project of mine but I'm not using the command handler, only the event store. I noticed there's no documentation for it.",
        "has_prod_signal": False,
        "gap_desc": "Standalone event-store usage has no docs - users must read the source to wire up appendToStream/readStream",
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: requires deciding the right public surface and writing a small, runnable sample.",
        "target_approach_file": "docs/eventStore/",
    },
    {"cve_id": None, "has_prod_signal": False, "has_workaround": False},
    {"similar_prs": [], "maintainer_responses": [
        {"body_quote": "If you're open to help on that, I'd be happy to take PR about it. Maybe you could join our Discord, and we can coordinate.", "issue_number": 284}
    ], "welcome_labels": []},
)

# 8658 — MongoDBEventStore prependMongoFilterWithProjectionPrefix ObjectId bug (issue 266). Real bug with stack trace.
upd(
    8658,
    "issue",
    "Fix prependMongoFilterWithProjectionPrefix TypeError when ObjectId values are used as filters",
    "When an event-store projection inline.find(...) filter contains an ObjectId value (e.g. as part of an array comparison), the call throws `TypeError: Cannot delete property '0' of [object Uint8Array]` from `prependMongoFilterWithProjectionPrefix`. Reproduction is straightforward via any ObjectId-typed projection key.",
    "In `packages/emmett-mongodb/src/eventStore/projections/prependMongoFilterWithProjectionPrefix.ts`, guard the delete-by-index path against non-object / typed-array values (use a hasOwnProperty + Array.isArray check, or coerce ObjectId to string for the filter-key path). Add a regression test using an ObjectId-typed value.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 9,
        "has_workaround": False,
        "prod_signal_quote": "Getting this error when a filter being passed to eventStore.projections.inline.find(...) is using an ObjectId",
        "has_prod_signal": False,
        "gap_desc": "prependMongoFilterWithProjectionPrefix throws TypeError on ObjectId filter values - MongoDB projections on ObjectId-typed fields crash",
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: helper assumes array-shaped values; needs a small type guard plus regression coverage.",
        "target_approach_file": "packages/emmett-mongodb/src/eventStore/projections/prependMongoFilterWithProjectionPrefix.ts",
    },
    {"cve_id": None, "has_prod_signal": False, "has_workaround": False},
    {"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
)

# 8656 — stream_metadata proposal (issue 385). Originally tagged performance but is a feature.
upd(
    8656,
    "feature",
    "Allow callers to attach `stream_metadata` when a stream is created (Postgres + SQLite)",
    "Both `emmett-postgresql` and `emmett-sqlite` define `stream_metadata JSONB NOT NULL` (or equivalent) and write it exactly once as the literal `{}`. Expose it as a per-call option so callers can attach tenant/region/tags at stream creation time.",
    "Add a `streamMetadata` option to `appendToStream` (and the underlying `HandleOptions<Store>`), persist it to the existing metadata column on first append, and read it back via a new `getStreamMetadata(streamName)` helper. PostgreSQL schema: `emmett-postgresql/src/eventStore/schema/appendToStream.ts:68-72`. SQLite schema: `emmett-sqlite/src/eventStore/schema/appendToStream.ts:175-184`.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 17,
        "has_workaround": True,
        "prod_signal_quote": "await eventStore.appendToStream(`shoppingCart-${cartId}`, [productAdded], { streamMetadata: { tenantId, region: 'eu-north-1' } });",
        "has_prod_signal": True,
        "target_has_stub": True,
        "target_related_files": [
            "packages/emmett-postgresql/src/eventStore/schema/appendToStream.ts",
            "packages/emmett-sqlite/src/eventStore/schema/appendToStream.ts",
        ],
        "feature_desc": "stream_metadata: per-stream JSON metadata written at creation",
        "gap_desc": "stream_metadata column exists but is hardcoded to empty; callers cannot attach tenant/region/tags today",
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: touches both Postgres and SQLite schemas, the appendToStream signature, and adds a read API; needs migration considerations for existing rows.",
        "target_approach_file": "packages/emmett-postgresql/src/eventStore/schema/appendToStream.ts",
    },
    {"cve_id": None, "has_prod_signal": True, "has_workaround": True},
    {"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
)

# 8657 — OTel / structured logging for workflow handler (issue 345). Originally performance; really observability.
upd(
    8657,
    "feature",
    "Add structured logging and OTel spans to the workflow handler for observability",
    "Add opt-in structured logging (debug gated on log level) and OpenTelemetry spans to `handleWorkflow.ts` so the first-hop store path, the workflow-prefix branch, and the second-hop processing path are visible during troubleshooting.",
    "In `packages/emmett/src/workflows/handleWorkflow.ts`, wrap each named decision point in an OTel span (e.g. `workflow.handle.first_hop`, `workflow.handle.second_hop`, `workflow.handle.prefix_resolve`) and emit a single structured log per decision gated on a `debug` log level so production throughput is unaffected. Default to no-op when neither OTel nor debug logging is configured.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 15,
        "has_workaround": False,
        "prod_signal_quote": "During troubleshooting of the output handler / double-hop workflow processing, all internal decision points were invisible. We had to manually inject console.log into framework code to diagnose what was happening.",
        "has_prod_signal": True,
        "target_has_stub": False,
        "target_related_files": ["packages/emmett/src/workflows/handleWorkflow.ts"],
        "feature_desc": "Structured logging + OTel spans for workflow handler",
        "gap_desc": "Workflow handler has zero observability; double-hop and first-hop decision points are invisible during troubleshooting",
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: must remain zero-overhead when neither logging nor OTel is enabled; needs careful span placement around concurrency boundaries.",
        "target_approach_file": "packages/emmett/src/workflows/handleWorkflow.ts",
    },
    {"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    {"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
)

con.commit()
con.close()
print("emmett done")