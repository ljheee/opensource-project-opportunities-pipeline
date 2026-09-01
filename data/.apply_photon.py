#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect('/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db')
cur = conn.cursor()

NOW = '2026-09-01T08:11:11.454181+00:00'

# 8702 — UNIQUE collision: 2187 already open with same (issue, issue:1093). DELETE.
cur.execute("DELETE FROM opportunities WHERE id=8702")

# 8704 — UNIQUE collision: 2189 already open with same (issue, issue:803). DELETE.
cur.execute("DELETE FROM opportunities WHERE id=8704")

# 8699 — UNIQUE collision: 2184 already open with same (issue, issue:143). DELETE.
# Also mis-labeled as security but it's a roadmap/feature request question.
cur.execute("DELETE FROM opportunities WHERE id=8699")

# 8698 — "Thread-per-core Architecture". Maintainer already explained Photon coroutines
# satisfy these requirements; not actionable as a contribution. DELETE.
cur.execute("DELETE FROM opportunities WHERE id=8698")

# 8703 — "Do I need to manually add source files like net/http/*.cpp" — this is a
# usage/CMake question, maintainer answered with documentation; not a contribution
# opportunity. DELETE.
cur.execute("DELETE FROM opportunities WHERE id=8703")

# 2185 — io_uring engine without io_uring_prep_poll_multishot. Keep as compatibility/issue.
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='compatibility',
  title='Use io_uring engine when kernel lacks io_uring_prep_poll_multishot',
  description='How can the io_uring event engine run on kernels older than what Photon requires for multishot poll? Maintainer suggests a kernel-version branch that falls back to one-shot poll.',
  impl_hint='In iouring-wrapper.cpp, detect kernel version and either skip multi-shot poll init or fall back to one-shot poll. Add liburing-version probe and gated code path.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=2185
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":0,"issue_count":5,"has_workaround":False,"prod_signal_quote":"Alright, I see. Please provide your OS type, kernel version, and liburing version. If able to reproduce, maybe we can add some if else code to by-pass calling multi-shot. Photon iouring module know exactly the current","has_prod_signal":True,"gap_desc":"Photon iouring engine assumes multi-shot poll support; older kernels are unsupported without code-path workaround"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Needs kernel-version detection and a fallback code path in iouring event engine; multi-shot vs one-shot semantics differ","target_approach_file":"src/io/iouring-wrapper.cpp"}),
  json.dumps({"cve_id":None,"has_prod_signal":True,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":[],"maintainer_responses":[{"author_association":"MAINTAINER","body_quote":"iouring multi-shot poll is not mandatory, one-shot poll also has similar performance. Looks like you are using the add_interest call of the event engine. Can you describe your scenario?"}]}),
))

# 2186 — Photon and ZeroMQ. User already integrated; thread on notification issue.
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='issue',
  title='Integrate ZeroMQ with Photon event engine (cascading + uring)',
  description='Author successfully integrated ZeroMQ sockets with Photon for simple cases. Cascading event io (uring master + epoll cascading + photon event loop for notifications) hits a lack-of-event problem for complex multi-router scenarios.',
  impl_hint='Investigate the lack-of-event scenario in cascading engine when a ZMQ router socket emits no events. Likely related to misregistration of fds or event-notification semantics in cascading.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=2186
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":0,"issue_count":18,"has_workaround":False,"prod_signal_quote":"","has_prod_signal":False,"gap_desc":"No first-class ZeroMQ integration in Photon; complex multi-router scenarios misbehave under cascading event engine"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Concurrency, event-engine semantics, and fd lifecycle in cascading mode","target_approach_file":"src/net/ and src/io/"}),
  json.dumps({"cve_id":None,"has_prod_signal":False,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":[],"maintainer_responses":[{"author_association":"MAINTAINER","body_quote":"Thank you for all these. I like ZeroMQ and used to use it a lot, your work is definitely welcomed to Photon."}]}),
))

# 2190 — Windows IOCP backend. Major architectural piece.
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='issue',
  title='Add Windows IOCP backend for Photon',
  description='Photon supports Linux-only event engines today (epoll, io_uring). Adding a Windows IOCP backend would let Photon run on Windows. Maintainer has already started porting the coroutine layer (thread.cpp) to Windows.',
  impl_hint='Add a new event engine under src/io/ following the existing epoll/iouring pattern, but using IOCP GetQueuedCompletionStatus. Reuse the already-started thread.cpp Windows port.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=2190
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":0,"issue_count":2,"has_workaround":False,"prod_signal_quote":"","has_prod_signal":False,"gap_desc":"Photon is Linux-only; no Windows IOCP backend, blocking Windows adoption"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Major architecture change; IOCP completion-port semantics differ from readiness-based engines (epoll/iouring)","target_approach_file":"src/io/ and thread/"}),
  json.dumps({"cve_id":None,"has_prod_signal":False,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":[],"maintainer_responses":[{"author_association":"MAINTAINER","body_quote":"Windows is not supported yet."},{"author_association":"MAINTAINER","body_quote":"I have made coroutine (thread.cpp) part of photon working in Windows."}]}),
))

# 2191 — Add more build options for separate lib, 1.0 packaging.
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='issue',
  title='Split Photon into per-module libraries and modernize build (C++ std option)',
  description='Author requests: (1) split Photon into separate libs (thread, net, rpc); (2) expose C++ standard as a CMake option (currently hardcoded C++14); (3) rename BUILD_TESTING to PHOTON_BUILD_TESTING; (4) hide internal symbols; (5) make submodule URL configurable.',
  impl_hint='Refactor CMakeLists.txt per module. Add a PHOTON_CXX_STANDARD option, rename test option, add visibility controls, and allow overriding submodule URLs via -D variables.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=2191
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":0,"issue_count":14,"has_workaround":False,"prod_signal_quote":"","has_prod_signal":False,"gap_desc":"Photon ships as a single monolithic library without per-module split, no C++ standard option, no symbol hiding"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Build-system refactor + ABI/symbol-hiding decisions + submodule URL override","target_approach_file":"CMakeLists.txt"}),
  json.dumps({"cve_id":None,"has_prod_signal":False,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":[],"maintainer_responses":[{"author_association":"MAINTAINER","body_quote":"I would suggest that: 1. We provide build options to allow for output as static or dynamic lib, whether build individual modules, whether link the modules together, whether link dependencies"}]}),
))

# 2182 — semaphore signal latency on AWS EC2.
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='performance',
  title='Investigate photon::semaphore signal latency (300-600ms) on AWS EC2',
  description='User reports photon::semaphore.signal() takes 300-600ms on AWS EC2 and asks for debugging guidance. Maintainer asks for vCPU count, branch, and engine used.',
  impl_hint='Reproduce under perf; check cross-vCPU semaphore path (cancel_wait) and vCPU interrupt routing. Likely tied to cross-vCPU scheduling when semaphore spans threads.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=2182
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":0,"issue_count":10,"has_workaround":False,"prod_signal_quote":"","has_prod_signal":True,"gap_desc":"photon::semaphore.signal() latency 300-600ms on AWS EC2 multi-vCPU; root cause unknown"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Concurrency/locking and vCPU scheduling; needs profiling with perf or equivalent","target_approach_file":"src/thread/"}),
  json.dumps({"cve_id":None,"has_prod_signal":True,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":[],"maintainer_responses":[{"author_association":"MAINTAINER","body_quote":"1. How many vCPUs are you using to synchronize with this semaphore? How many cores are there in your EC2. 2. Does this issue appear on other platforms or physical machines?"}]}),
))

# mark task 1538 done + project active
cur.execute("UPDATE tasks SET status='done', finished_at=? WHERE id=1538", (NOW,))
cur.execute("UPDATE projects SET status='active' WHERE id='alibaba/PhotonLibOS' AND status='analyzing'")

conn.commit()
print("photon updates committed")
print("rows updated for photon:")
for row in cur.execute("SELECT id, status, source_type FROM opportunities WHERE id IN (2185,2186,2190,2191,2182)"):
    print(row)
print("rows deleted for photon:")
for row in cur.execute("SELECT id, status, source_type FROM opportunities WHERE id IN (8698,8703,8699,8702,8704)"):
    print(row)