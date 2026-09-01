#!/usr/bin/env python3
"""Apply capnweb (task 1520) draft judgments."""
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

# 8646 — Cap'n Proto bridge (issue 179)
upd(
    8646,
    "issue",
    "Bridge Cap'n Web to IDL-based Cap'n Proto servers (C++/Rust/Go)",
    "Allow servers written against Cap'n Proto IDL (C++/Rust/Go) to be consumed by Cap'n Web TypeScript clients. Needs: (1) a code generator that emits TypeScript types from `.capnp` files, and (2) a proxy implementation that converts between Cap'n Web RPC protocol and Cap'n Proto. Most heavy lifting is already implemented in the existing Cap'n Proto Java reference.",
    "Add a `.capnp -> .d.ts` codegen step (likely reusing capnpc-ts) and a session/proxy that walks Cap'n Web messages into Cap'n Proto PackedMessage calls; can be staged behind a separate package entrypoint.",
    {
        "canonical_impl_url": "https://github.com/capnproto/capnproto-java/tree/master/runtime/src/main/java/org/capnproto",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 1,
        "issue_count": 19,
        "has_workaround": False,
        "prod_signal_quote": "People writing servers in languages like C++, Rust, or Go probably prefer to use an IDL+code generator like Cap'n Proto, rather than use TypeScript types.",
        "has_prod_signal": True,
        "gap_desc": "Cap'n Web is TS-only today; no bridge to IDL-based Cap'n Proto servers written in C++/Rust/Go - blocks multi-language server interop",
    },
    {
        "canonical_impl_url": "https://github.com/capnproto/capnproto-java/tree/master/runtime/src/main/java/org/capnproto",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: requires a new codegen pipeline + protocol bridging; no existing TypeScript-to-Cap'n Proto proxy to copy from.",
        "target_approach_file": "packages/core/src/rpc/",
    },
    {"cve_id": None, "has_prod_signal": True, "has_workaround": False},
    {
        "similar_prs": [],
        "maintainer_responses": [
            {
                "body_quote": "The team plans to work on this in the coming months. Sorry but we don't really sponsor outside contractors for this sort of thing; we generally prefer to keep it in house.",
                "author_association": "OWNER",
                "issue_number": 179,
            }
        ],
        "welcome_labels": [],
    },
)

# 8647 — Cap'n Proto in Wasm (issue 181)
upd(
    8647,
    "issue",
    "Allow Wasm workers to implement Cap'n Proto interfaces directly",
    "Enable a Wasm-targeting worker (e.g. Rust compiled to Wasm) to be the server side of a Cap'n Web client. Stacks with the Cap'n Proto bridge (#179) so that an end-to-end Rust-server + TS-client flow becomes possible.",
    "Expose a Cap'n Proto message handler compatible with the workerd fetch/RPC boundary; likely a new entry in `packages/core/src/wasm/` plus a sample Rust worker crate that links capnp-rpc.",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 1,
        "issue_count": 8,
        "has_workaround": False,
        "prod_signal_quote": "This could stack with the Cap'n Proto bridge #179 to allow someone to write a worker in Rust Wasm and call it with a Cap'n Web client.",
        "has_prod_signal": False,
        "gap_desc": "No Wasm-side server story for Cap'n Web today; Rust-wasm workers cannot expose Cap'n Proto interfaces to TS clients",
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: requires workerd/Wasm FFI plumbing and a sample Rust crate; needs the bridge from #179 to land first.",
        "target_approach_file": "packages/core/src/wasm/",
    },
    {"cve_id": None, "has_prod_signal": False, "has_workaround": False},
    {"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
)

# 8648 — ReadableStream through forwarded stub (issue 228)
upd(
    8648,
    "issue",
    "ReadableStream returned through a forwarded stub throws (broker/dup path bug)",
    "When a method returns a ReadableStream and the stub holding the stream is forwarded via a broker (broker.dup() returned to a third party), the caller sees an exception instead of receiving the stream. Direct session works fine; only the forwarded path is broken.",
    "Reproduce with: (1) broker<->child session, child returns a ReadableStream; (2) caller<->broker session where broker returns childStub.dup(); (3) caller awaits the stream. Trace through the stream-message lifecycle in `packages/core/src/rpc/streams.ts` and ensure the stream payload survives the broker hop (likely a missing Disown/Send translation for stream payload handles).",
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 16,
        "has_workaround": True,
        "prod_signal_quote": "A ReadableStream returned by an RPC method works when the caller holds a direct session to the target. It throws when the call is forwarded through an intermediate session, such as when a broker returns a dup of a stub it holds to a third party.",
        "has_prod_signal": False,
        "gap_desc": "Forwarded-stub stream payloads are dropped/throw - broker-pattern interop breaks for any streaming response",
    },
    {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "Hard because: involves concurrency and the handle-pipeline logic in the RPC core; symptom only appears via the broker hop so repro is non-trivial.",
        "target_approach_file": "packages/core/src/rpc/streams.ts",
    },
    {"cve_id": None, "has_prod_signal": False, "has_workaround": True},
    {"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
)

con.commit()
con.close()
print("capnweb done")