#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect('/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db')
cur = conn.cursor()

NOW = '2026-09-01T08:09:05.569348+00:00'

# 8690 — re-label performance -> issue, keep source_ref
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='issue',
  title='Macro for generating the Iden from a given Struct',
  description='Author seeks a macro (derive or attribute) to auto-generate the Iden enum from a struct, avoiding the maintenance burden of duplicating an enum and a struct. Maintainer prefers attribute macro because the macro generates structs rather than implementing traits.',
  impl_hint='Add an attribute/derive macro in sea-query-attr or sea-query-derive that emits an enum with table and column variants from a struct definition. See referenced discussion in the issue for an example API surface.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=8690
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":2,"issue_count":20,"has_workaround":False,"prod_signal_quote":"it produces some unnecessary boilerplate with the Iden when I am already using structs as my models. I understand that Iden is not really a replacement, but maintaining both an enum and a struct is not very efficient for me.","has_prod_signal":True,"gap_desc":"Manual duplication of enum-based Iden and struct models in sea-query, with no derive/attribute macro to keep them in sync"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Requires macro implementation; attribute macro can emit structs, derive macro emits trait impls. Maintainer preference is attribute macro path.","target_approach_file":"sea-query-attr/"}),
  json.dumps({"cve_id":None,"has_prod_signal":True,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":[],"maintainer_responses":[{"author_association":"MAINTAINER","body_quote":"Hi there. Thank you for your suggestion. It may not be well-advertised, but do you think https://github.com/SeaQL/sea-query/blob/master/sea-query-attr/tests/pass/default.rs serves the need?"},{"author_association":"MAINTAINER","body_quote":"the original contributor thinks it is more appropriate to make it an attribute macro instead of a derive macro, since it generates structs instead of implementing traits"}]}),
))

# 8691 — re-label performance -> issue (feature request)
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='issue',
  title='Add Postgres bulk insert API with UNNEST and ARRAYs',
  description='Provide a bulk insert helper that emits INSERT INTO t(a,b) VALUES (1, unnest(array[1,2,3])) so users avoid Postgres parameter-count limits and ship a smaller prepared statement for OLAP-style loads.',
  impl_hint='Add a typed builder for multi-row inserts that emits UNNEST/ARRAY-based SQL on Postgres. Fallback to existing placeholders for other dialects.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=8691
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":1,"issue_count":21,"has_workaround":False,"prod_signal_quote":"Avoids parameter count limitation as the the inserted values are an array. In general a smaller query before replacing placeholders.","has_prod_signal":True,"gap_desc":"No built-in bulk insert API leveraging Postgres UNNEST/ARRAY in sea-query, blocking OLAP-style batch loads"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Requires dialect-aware codegen; needs careful testing against multi-dialect Postgres INSERT semantics","target_approach_file":"src/postgres/"}),
  json.dumps({"cve_id":None,"has_prod_signal":True,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":[],"maintainer_responses":[{"author_association":"MAINTAINER","body_quote":"Thank you for the sponsor. I would put this on my stack."},{"author_association":"MAINTAINER","body_quote":"Sorry for the delay. Yes, we have some time now as 1.0 is concluding. I have some plan regarding OLAP, including bulk data inserts and some extensions to TimescaleDB"}]}),
))

# 8692 — re-label performance -> issue (ergonomics)
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='issue',
  title='Re-expose Postgres full-text search functions with regconfig-typed parameters',
  description='The Postgres full-text search helpers (to_tsquery, to_tsvector, phraseto_tsquery, plainto_tsquery, websearch_to_tsquery) currently accept regconfig as u32, which is unergonomic at call sites.',
  impl_hint='Wrap each helper to accept PgRegConfig (or Option<PgRegConfig>) as a strongly typed parameter, mapping internally to regtype/oid cast.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=8692
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":1,"issue_count":23,"has_workaround":False,"prod_signal_quote":"the way that the Postgres functions ... are exposed in sea-query makes them unergonomic.","has_prod_signal":False,"gap_desc":"Postgres FTS helpers exposed with regconfig: u32, lacking typed wrapper for ergonomic calls"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Requires adding typed wrapper across the FTS function set without breaking existing call sites","target_approach_file":"src/postgres/func/"}),
  json.dumps({"cve_id":None,"has_prod_signal":False,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":[],"maintainer_responses":[]}),
))

# 8693 — keep as issue
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='issue',
  title='IdenIter / IdenList macro to derive all columns at once',
  description='Author revives #90 requesting a macro that yields an iterator/list of Iden covering all columns of a struct, so users can do INSERT/SELECT INTO without listing each column manually.',
  impl_hint='Add an IdenIter/IdenList derive that emits a method returning all column variants of the struct. Optionally coordinate with SeaORM DeriveIden so the implementation can live either in sea-query or sea-orm.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=8693
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":1,"issue_count":23,"has_workaround":True,"prod_signal_quote":"I am reviving #90 because I had time","has_prod_signal":False,"gap_desc":"No derive/macro that emits all columns of a struct as Iden variants for ergonomic SELECT/INSERT in sea-query"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Macro engineering and API surface decision (sea-query vs sea-orm); not a runtime hot path","target_approach_file":"sea-query-derive/"}),
  json.dumps({"cve_id":None,"has_prod_signal":False,"has_workaround":True}),
  json.dumps({"similar_prs":[{"number":239,"title":"With clause and with queries","merged":True,"url":"https://github.com/SeaQL/sea-query/pull/239","age_days":1689,"maintainer_comment":""}],"welcome_labels":[],"maintainer_responses":[{"author_association":"MAINTAINER","body_quote":"I think this is doable in SeaORM, because it is shipping its own version of DeriveIden"}]}),
))

# 8694 — keep as compatibility
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='compatibility',
  title='UNION of two SELECTs does not wrap first query in parentheses',
  description='When the first query of a UNION contains ORDER BY and/or LIMIT, sea-query does not wrap it in parentheses, producing invalid SQL on at least Postgres and breaking ordering.',
  impl_hint='In the UNION builder, detect when the LHS has ORDER BY/LIMIT/OFFSET and emit parentheses around the subquery, or rely on user-side subquery.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=8694
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":1,"issue_count":19,"has_workaround":False,"prod_signal_quote":"This leads to a wrong query (with the postgresql backend at least), when the first query of the union contains order by and/or limit statements","has_prod_signal":True,"gap_desc":"UNION of two SELECTs in sea-query emits SQL missing parens around LHS, breaking ORDER BY/LIMIT semantics on Postgres"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Requires SQL builder changes and dialect coverage (sqlite polyfill also discussed)","target_approach_file":"src/query/union.rs"}),
  json.dumps({"cve_id":None,"has_prod_signal":True,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":[],"maintainer_responses":[{"author_association":"MAINTAINER","body_quote":"I think the reason for the current issue is, this is not valid SQL in sqlite. A possible solution is to implement a polyfill for sqlite like select * from (subquery) union select * from (subquery)"}]}),
))

# mark task 1536 done + project active
cur.execute("UPDATE tasks SET status='done', finished_at=? WHERE id=1536", (NOW,))
cur.execute("UPDATE projects SET status='active' WHERE id='SeaQL/sea-query' AND status='analyzing'")

conn.commit()
print("sea-query updates committed")
print("rows updated for sea-query:")
for row in cur.execute("SELECT id, status, source_type FROM opportunities WHERE id IN (8690,8691,8692,8693,8694)"):
    print(row)