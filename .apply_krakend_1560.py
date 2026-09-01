"""Apply Stage 4 v2 judgments for task 1560 (krakend/krakend-ce)."""
import json
import sqlite3

DB = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"
TS = "2026-09-01T11:00:00+00:00"
PROJECT_ID = "krakend/krakend-ce"
TASK_ID = 1560

UPDATES = [
    # 3671 — issue:1012 plugin build xxhash mismatch → issue
    dict(
        oid=3671,
        source_ref="issue:1012",
        source_type="issue",
        title="Fix xxhash version mismatch in KrakenD plugin loader (Redis rate-limit plugin fails to load)",
        description=(
            "When compiling a Go plugin against go-redis/v9 the resulting .so fails to load into "
            "KrakenD because the plugin links a different xxhash version than KrakenD embeds. This "
            "is a classic Go plugin version-skew issue surfaced via dep mismatch on xxhash. "
            "Make KrakenD's plugin loader pin or normalise xxhash, or document and enforce a "
            "single xxhash version in the plugin loader path."
        ),
        impl_hint=(
            "Investigate the plugin loader path under krakend-ce (plugin handler invocation). "
            "Reproduce by building a sample plugin that imports github.com/redis/go-redis/v9, "
            "then load it into KrakenD and observe the symbol-version error. Fix by either "
            "embedding the same xxhash version in the core, or stripping the conflicting "
            "dependency. The maintainer's `check-plugin -f` recommendation already implies this "
            "is a known class of problem."
        ),
        value_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 0,
            "issue_count": 32,
            "has_workaround": True,
            "prod_signal_quote": (
                "When restarting KrakenD after compiling the plugin as a .so ... fails to load"
            ),
            "has_prod_signal": True,
            "gap_desc": (
                "KrakenD plugin loader does not normalise xxhash dependency versions, so plugins "
                "importing go-redis/v9 fail to load"
            ),
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: Go plugin model requires exact symbol matching across the core "
                "and plugin binary; changes must touch the plugin loader/dependency graph; no "
                "canonical reference implementation available"
            ),
            "target_approach_file": "krakend-ce/plugin/handler.go (approx — find plugin loader entry)",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": True},
        maintainer_evidence={
            "similar_prs": [],
            "maintainer_responses": [
                {
                    "author_association": "MAINTAINER",
                    "body_quote": "Can you try using the `check-plugin` command? The `-f` flag will output the required `go get` commands to fix the dependency issue.",
                    "issue_number": 1012,
                },
                {
                    "author_association": "MAINTAINER",
                    "body_quote": "Redis is supported on KrakenD Enterprise. Whether Redis integration in plugins is officially supported is currently ambiguous in the OSS build.",
                    "issue_number": 1012,
                },
            ],
            "welcome_labels": [],
        },
    ),
    # 8873 — security issue:996 high-severity vuln in oauth2/jws → security
    dict(
        oid=8873,
        source_ref="issue:996",
        source_type="security",
        title="Upgrade golang.org/x/oauth2/jws in KrakenD CE (high-severity transitive vulnerability)",
        description=(
            "KrakenD CE bundles golang.org/x/oauth2/jws @ v0.22.0 which has a reported "
            "high-severity CVE. Bump the dependency and verify no API breakage across oauth2/jws "
            "call sites."
        ),
        impl_hint=(
            "Run `go list -m -versions golang.org/x/oauth2/jws`, choose the latest patched "
            "minor, then `go get golang.org/x/oauth2/jws@<new>` and `go mod tidy`. Run the full "
            "test suite, in particular the auth/validator tests under the auth components."
        ),
        value_evidence={
            "cve_id": None,
            "vulnerable_dep": "golang.org/x/oauth2/jws @ v0.22.0",
            "fixed_in_dep": "latest patched v0.22.x or v0.23.x",
            "canonical_fixed": True,
            "peer_fixed": [],
            "affected_file": "go.mod",
            "affected_api": "golang.org/x/oauth2/jws",
            "attack_surface": "Any JWS verification path in KrakenD CE; specific CVE details depend on the reported version",
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: requires verifying no public API surface broke across the bump; "
                "cross-module impact assessment needed"
            ),
            "target_approach_file": "go.mod",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": False, "has_workaround": False},
        maintainer_evidence={"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
    ),
    # 8874 — issue 982 altering 500 for context canceled → issue
    dict(
        oid=8874,
        source_ref="issue:982",
        source_type="issue",
        title="Allow configuring the HTTP status returned for context-cancelled upstream calls",
        description=(
            "KrakenD currently surfaces upstream context-cancelled calls as HTTP 500, which is "
            "misleading because the failure is client-driven (client closed connection). Allow "
            "operators to choose a more accurate status (e.g., 499 / 502 / 503) via config."
        ),
        impl_hint=(
            "Locate the proxy/handler that translates context errors into HTTP status (likely in "
            "router or proxy package). Add a config flag under service config "
            "(`error_status_on_cancel`) and wire it through to the status mapping."
        ),
        value_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 6,
            "issue_count": 24,
            "has_workaround": False,
            "prod_signal_quote": "",
            "has_prod_signal": False,
            "gap_desc": (
                "KrakenD surfaces context-cancelled upstream errors as 500, polluting "
                "real-error metrics and confusing operators"
            ),
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: requires plumbing a new config key through the proxy chain and "
                "adding tests for each cancellation path"
            ),
            "target_approach_file": "proxy/proxy.go (approx)",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": False, "has_workaround": False},
        maintainer_evidence={"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
    ),
    # 8875 — security 788 missing plugins severity → reclassify to issue (UX/diagnostics)
    dict(
        oid=8875,
        source_ref="issue:788",
        source_type="issue",
        title="Improve error severity and logging when KrakenD loads with missing plugins",
        description=(
            "When KrakenD is configured with plugin handlers that cannot be loaded, the failure "
            "is logged at debug level, leaving production operators in the dark. Promote the "
            "failure to error/warn and emit a clear startup-level diagnostic."
        ),
        impl_hint=(
            "Find the plugin loader initialization in main.go or plugin package. When a plugin "
            "referenced in config cannot be loaded, log at error level (and exit non-zero if the "
            "plugin is required). Add a CLI flag `krakend-ce check --config krakend.json --strict`."
        ),
        value_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 3,
            "issue_count": 32,
            "has_workaround": False,
            "prod_signal_quote": (
                "Most relevant log messages were on the debug level and I'm using the info level "
                "on production"
            ),
            "has_prod_signal": True,
            "gap_desc": (
                "KrakenD silently degrades or runs without a plugin due to debug-level "
                "plugin-load failures"
            ),
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: requires distinguishing between 'optional' and 'required' plugins "
                "in the config schema; needs changes to logging levels and exit codes"
            ),
            "target_approach_file": "krakend-ce/main.go (approx plugin init)",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
        maintainer_evidence={
            "similar_prs": [],
            "maintainer_responses": [
                {
                    "author_association": "MAINTAINER",
                    "body_quote": (
                        "Our philosophy is that you should test everything locally before "
                        "pushing it to production, and plugin testing should be part of your "
                        "CI/CD pipeline. Nevertheless, your point about visibility is fair."
                    ),
                    "issue_number": 788,
                },
            ],
            "welcome_labels": [],
        },
    ),
    # 8876 — issue 981 ARM/ARM64 binaries → issue
    dict(
        oid=8876,
        source_ref="issue:981",
        source_type="issue",
        title="Publish official ARM and ARM64 binaries for KrakenD CE",
        description=(
            "KrakenD does not ship ARM/ARM64 binaries, making it impossible to build ARM-based "
            "Docker images without an extra cross-compile step. Add ARM64 (linux/arm64) and "
            "optionally ARMv7 (linux/arm/v7) to the release matrix."
        ),
        impl_hint=(
            "Update the release workflow (likely .github/workflows/release.yml) to add matrix "
            "entries for GOARCH=arm64 and GOARCH=arm. Use the same cross-compile flags already "
            "in the build script. Update the README download table to list ARM URLs."
        ),
        value_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 2,
            "issue_count": 29,
            "has_workaround": True,
            "prod_signal_quote": "I want to build the arm based image but it's not possible to do so directly",
            "has_prod_signal": False,
            "gap_desc": "KrakenD release pipeline does not produce ARM64 or ARMv7 binaries",
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: requires cross-compile infrastructure and verifying tests on ARM "
                "emulators; not conceptually hard"
            ),
            "target_approach_file": ".github/workflows/release.yml",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": False, "has_workaround": True},
        maintainer_evidence={"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
    ),
    # 8877 — security 852 complex keys in keys_to_sign → security
    dict(
        oid=8877,
        source_ref="issue:852",
        source_type="security",
        title="Support complex key expressions in keys_to_sign property",
        description=(
            "KrakenD's `keys_to_sign` accepts a flat list of key names. Power users want "
            "nested / templated key expressions for fine-grained signing on per-endpoint basis. "
            "Extend `keys_to_sign` to accept expressions / dotted paths, with documentation and "
            "a regression test."
        ),
        impl_hint=(
            "Locate the signing handler (likely under the jwt plugin or signer middleware). "
            "Refactor `keys_to_sign` parsing to support dotted paths and template expressions. "
            "Add unit tests covering nested keys and per-route signing."
        ),
        value_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 1,
            "issue_count": 30,
            "has_workaround": False,
            "prod_signal_quote": "",
            "has_prod_signal": False,
            "gap_desc": (
                "KrakenD's keys_to_sign property does not support complex / nested key "
                "expressions; only flat lists are accepted"
            ),
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: signing is a security-critical surface; backward compatibility "
                "with existing flat keys_to_sign configs must be preserved"
            ),
            "target_approach_file": "plugin/jwt-signer (approx)",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": False, "has_workaround": False},
        maintainer_evidence={
            "similar_prs": [],
            "maintainer_responses": [
                {
                    "author_association": "MAINTAINER",
                    "body_quote": "this functionality is not currently supported",
                    "issue_number": 852,
                },
                {
                    "author_association": "MAINTAINER",
                    "body_quote": (
                        "I will leave this issue open for a while so people can upvote the "
                        "functionality with a :+1: . It is the first time I've seen this "
                        "requirement in six years, so I don't think it is very common."
                    ),
                    "issue_number": 852,
                },
            ],
            "welcome_labels": [],
        },
    ),
    # 8878 — perf 976 AWS S3 signatures % → issue (URL-encoding bug)
    dict(
        oid=8878,
        source_ref="issue:976",
        source_type="issue",
        title="Fix AWS S3 signature corruption when keys contain % characters",
        description=(
            "KrakenD modifies AWS S3 signatures when the signing key contains `%` characters "
            "(URL-decoding step strips or mangles `%` tokens). Investigate and preserve the "
            "original key during signing."
        ),
        impl_hint=(
            "Locate the AWS S3 backend or signer code (likely under proxy/backend/aws or a "
            "dedicated signer). Audit all places that call url.PathEscape / url.QueryEscape / "
            "unquote on the signing key path and ensure raw form is preserved through signing."
        ),
        value_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 1,
            "issue_count": 31,
            "has_workaround": False,
            "prod_signal_quote": "",
            "has_prod_signal": False,
            "gap_desc": (
                "KrakenD's AWS S3 backend corrupts signatures when S3 keys contain the % "
                "character"
            ),
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: AWS SigV4 has strict canonical-request rules; reproducing "
                "requires a real S3 bucket with % in key; no canonical reference"
            ),
            "target_approach_file": "proxy/backend/aws or signer module (approx)",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": False, "has_workaround": False},
        maintainer_evidence={"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
    ),
    # 8879 — compat 787 graceful restart tableflip → issue (feature request, real ops pain)
    dict(
        oid=8879,
        source_ref="issue:787",
        source_type="issue",
        title="Implement graceful restart for KrakenD CE using tableflip (zero-downtime reload)",
        description=(
            "Restarting KrakenD always incurs a short downtime: the old process closes the HTTP "
            "listen socket, the new process binds, and any in-flight requests fail. Use "
            "cloudflare/tableflip to hand the socket from old process to new, enabling "
            "zero-downtime reload on config change."
        ),
        impl_hint=(
            "Import github.com/cloudflare/tableflip. Refactor main.go to create the upgrader, "
            "bind the listener, and call Upgrade() before serving. Hook config-reload signal to "
            "call Upgrader.Upgrade() and exit old process. Add integration test that starts two "
            "processes sharing the socket."
        ),
        value_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 1,
            "issue_count": 31,
            "has_workaround": False,
            "prod_signal_quote": (
                "Restarting krakend always comes with a short downtime on that machine, as the "
                "old process is shutting down, thus closing the HTTP listen socket, and then a "
                "new process is starting"
            ),
            "has_prod_signal": True,
            "gap_desc": (
                "KrakenD has no graceful restart path; every reload drops in-flight requests"
            ),
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: involves concurrency/locking on the socket fd across processes; "
                "needs signal handling and integration testing across two processes"
            ),
            "target_approach_file": "krakend-ce/main.go",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": True, "has_workaround": False},
        maintainer_evidence={"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
    ),
    # 8880 — security 1050 DPoP → security (real OAuth feature gap)
    dict(
        oid=8880,
        source_ref="issue:1050",
        source_type="security",
        title="Add DPoP (RFC 9449) access-token validation in KrakenD",
        description=(
            "KrakenD does not currently validate DPoP-bound access tokens, leaving deployments "
            "that require DPoP unable to use KrakenD as an OAuth resource server. Implement "
            "DPoP proof validation per RFC 9449."
        ),
        impl_hint=(
            "Add a DPoP verifier under the auth/validator middleware. Parse the DPoP proof "
            "header, verify the htu/htm/iat claims, validate the JWK thumbprint against the "
            "access token's cnf claim, and reject mismatches. Add unit tests and a config flag "
            "(`auth.dpop_required`)."
        ),
        value_evidence={
            "cve_id": None,
            "vulnerable_dep": "",
            "fixed_in_dep": "",
            "canonical_fixed": True,
            "peer_fixed": [],
            "affected_file": "auth/validator (approx)",
            "affected_api": "DPoP-bound OAuth access tokens (RFC 9449)",
            "attack_surface": (
                "OAuth resource-server path: missing DPoP validation allows token replay attacks "
                "in deployments requiring sender-constrained tokens"
            ),
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: implementing RFC 9449 correctly requires JWK thumbprint "
                "computation, htu/htm binding, and integration with the existing JWT validator "
                "pipeline"
            ),
            "target_approach_file": "auth/validator (approx)",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": False, "has_workaround": False},
        maintainer_evidence={"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
    ),
    # 8881 — security 961 CORS auth 403 → issue (bug, not security vuln)
    dict(
        oid=8881,
        source_ref="issue:961",
        source_type="issue",
        title="Fix CORS header not added when auth/validator returns 403",
        description=(
            "When the auth/validator rejects a preflight or actual request with 403, KrakenD "
            "does not add the configured CORS headers, causing browser clients to fail with a "
            "generic CORS error masking the real 403 reason."
        ),
        impl_hint=(
            "Locate the CORS middleware in router/proxy and ensure it runs before the "
            "auth/validator returns the 403, so the Access-Control-Allow-Origin/Headers are "
            "always present on error responses. Add regression test asserting CORS headers on "
            "403 from auth/validator."
        ),
        value_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "peer_impl_urls": [],
            "issue_reactions": 1,
            "issue_count": 32,
            "has_workaround": False,
            "prod_signal_quote": "",
            "has_prod_signal": False,
            "gap_desc": (
                "KrakenD's CORS middleware short-circuits when auth/validator returns 403, "
                "hiding the real error from browser clients"
            ),
        },
        difficulty_evidence={
            "canonical_impl_url": "",
            "canonical_impl_loc": 0,
            "why_hard": (
                "Hard because: middleware ordering in the proxy chain is non-trivial; needs "
                "regression coverage for each 4xx error path"
            ),
            "target_approach_file": "router/gin or proxy CORS middleware",
        },
        urgency_evidence={"cve_id": None, "has_prod_signal": False, "has_workaround": False},
        maintainer_evidence={"similar_prs": [], "maintainer_responses": [], "welcome_labels": []},
    ),
]


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    try:
        for u in UPDATES:
            # Pre-flight: check for UNIQUE collision on (project_id, source_type, source_ref)
            cur.execute(
                """SELECT id, status FROM opportunities
                   WHERE project_id=? AND source_type=? AND source_ref=? AND id<>?""",
                (PROJECT_ID, u["source_type"], u["source_ref"], u["oid"]),
            )
            collision = cur.fetchone()
            if collision:
                # Per stage4-v2-dedup-unique-collision memory: DELETE the draft, keep the open row
                cur.execute("DELETE FROM opportunities WHERE id=?", (u["oid"],))
                print(
                    f"DELETE draft {u['oid']} (collides with existing row {collision[0]} "
                    f"status={collision[1]} on {u['source_type']}/{u['source_ref']})"
                )
                continue
            cur.execute(
                """UPDATE opportunities
                   SET status='open', source_type=?, title=?, description=?, impl_hint=?,
                       value_evidence=?, difficulty_evidence=?, urgency_evidence=?, maintainer_evidence=?,
                       value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
                   WHERE id=?""",
                (
                    u["source_type"],
                    u["title"],
                    u["description"],
                    u["impl_hint"],
                    json.dumps(u["value_evidence"], ensure_ascii=False),
                    json.dumps(u["difficulty_evidence"], ensure_ascii=False),
                    json.dumps(u["urgency_evidence"], ensure_ascii=False),
                    json.dumps(u["maintainer_evidence"], ensure_ascii=False),
                    u["oid"],
                ),
            )
            print(f"UPDATE {u['oid']}: {cur.rowcount} row(s) -> open/{u['source_type']}")
        # Mark task done + project active
        cur.execute(
            "UPDATE tasks SET status='done', finished_at=? WHERE id=? AND status='analyzed'",
            (TS, TASK_ID),
        )
        print(f"task {TASK_ID}: {cur.rowcount} row(s) -> done")
        cur.execute(
            "UPDATE projects SET status='active' WHERE id=? AND status='analyzing'",
            (PROJECT_ID,),
        )
        print(f"project {PROJECT_ID}: {cur.rowcount} row(s) -> active")
        con.commit()
        print("COMMITTED")
    finally:
        con.close()


if __name__ == "__main__":
    main()