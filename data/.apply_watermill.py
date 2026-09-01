#!/usr/bin/env python3
import sqlite3
import json

conn = sqlite3.connect('/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db')
cur = conn.cursor()

NOW = '2026-09-01T08:06:37.791082+00:00'

# 8682 — UNIQUE collision: 3287 already verified with same (issue, issue:5). DELETE draft.
cur.execute("DELETE FROM opportunities WHERE id=8682")

# 8685 — UNIQUE collision: 3289 already open with (issue, issue:433). DELETE this draft (current is compatibility).
cur.execute("DELETE FROM opportunities WHERE id=8685")

# 8689 — compatibility: deadlock in AMQP subscriber. Keep as compatibility.
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='compatibility',
  title='watermill-amqp: deadlock on delivery acknowledgement timeout',
  description='Watermill AMQP subscriber can deadlock on channel lock when RabbitMQ ack times out (e.g. AWS managed RabbitMQ recently introduced this timeout). Repro provided by author.',
  impl_hint='In AMQP subscriber, do not hold channel mutex across blocking ack/nack waits; use context with timeout and propagate the deadline through the channel ops.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=8689
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":2,"issue_count":37,"has_workaround":False,"prod_signal_quote":"Here is a example what reproduces the issue https://github.com/prochac/ThreeDotsLabs_watermill_I242","has_prod_signal":True,"gap_desc":"watermill-amqp subscriber deadlocks on channel lock when upstream RabbitMQ ack times out"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Concurrency/locking; channel mutex held across blocking calls; needs careful test against streadway/amqp behavior","target_approach_file":"_examples/internal-pub-sub/amqp/"}),
  json.dumps({"cve_id":None,"has_prod_signal":True,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":[],"maintainer_responses":[]}),
))

# 3288 — Eventstore Pub/Sub. help wanted label.
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='issue',
  title='Add Eventstore Pub/Sub implementation for Watermill',
  description='Add an Eventstore (https://eventstore.com/) Pub/Sub implementation so Watermill users can publish/subscribe against an Eventstore cluster. Issue notes design references go.geteventstore and go-gesclient.',
  impl_hint='Create a new module following https://watermill.io/docs/pub-sub-implementing/. Start by reviewing go.geteventstore and go-gesclient semantics for catching up subscriptions.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=3288
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":3,"issue_count":28,"has_workaround":False,"prod_signal_quote":"","has_prod_signal":False,"gap_desc":"No native Eventstore Pub/Sub adapter in Watermill; community-requested since 2018"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Need to understand Eventstore subscription model (catch-up, competing consumers) and wire to Watermill PubSub interface","target_approach_file":"_examples/internal-pub-sub/eventstore/"}),
  json.dumps({"cve_id":None,"has_prod_signal":False,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":["help wanted"],"maintainer_responses":[{"author_association":"MAINTAINER","body_quote":"If you have some knowledge about EventStore and you can provide some ideas/guidelines it may be helpful for me or someone who would like to implement it"}]}),
))

# 3290 — MongoDB Pub/Sub
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='issue',
  title='Add MongoDB Pub/Sub implementation for Watermill',
  description='Implement a MongoDB-backed Pub/Sub for Watermill. Issue suggests modelling after the SQL implementation in ThreeDotsLabs/watermill-sql due to similar characteristics.',
  impl_hint='Use change streams or polling-based SQL pattern from watermill-sql; publish by writing to a Mongo collection, subscribe via change streams/resumable cursors.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=3290
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":2,"issue_count":30,"has_workaround":False,"prod_signal_quote":"You can start with your own repository. If you would like, we can then move it to our space and help you make the library production ready.","has_prod_signal":True,"gap_desc":"No MongoDB Pub/Sub adapter for Watermill; maintainer open to moving a community impl into their org"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Change-streams semantics, resumability, and offset tracking required for production-ready subscription","target_approach_file":"_examples/internal-pub-sub/mongodb/"}),
  json.dumps({"cve_id":None,"has_prod_signal":True,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":["help wanted"],"maintainer_responses":[{"author_association":"MAINTAINER","body_quote":"Hey @cunyat! You can start with your own repository. If you would like, we can then move it to our space and help you make the library production ready."}]}),
))

# 8680 — Sagas support. 25 reactions.
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='issue',
  title='Add Sagas support to Watermill',
  description='Long-standing feature request for Saga support in Watermill. Maintainer pointed to czeslavo/process-manager (a Process Manager example using Watermill) as similar in spirit.',
  impl_hint='Build on the Process Manager example (czeslavo/process-manager). Define a Saga abstraction over Watermill handlers with compensating actions and persistent state.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=8680
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":["https://github.com/czeslavo/process-manager"],"issue_reactions":25,"issue_count":0,"has_workaround":False,"prod_signal_quote":"","has_prod_signal":True,"gap_desc":"Watermill lacks a first-class Saga abstraction; users implement custom Process Manager pattern instead"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Saga semantics (compensation, persistence, timeouts) and consistent interface across all Watermill PubSub backends","target_approach_file":"_examples/"}),
  json.dumps({"cve_id":None,"has_prod_signal":True,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":[],"maintainer_responses":[{"author_association":"MAINTAINER","body_quote":"@czeslavo prepared a pretty nice example of Process Manager implementation with Watermill here: https://github.com/czeslavo/process-manager. It is not Saga, but it is pretty similar"}]}),
))

# 8681 — Allow choosing the nack method
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='issue',
  title='Allow choosing the Nack method on a per-message basis',
  description='Currently Watermill nacks with a single global method. User requests Message.Nack(method) so different consumers can pick NackRequeue, NackDiscard, or NackDelay per message.',
  impl_hint='Add a NackMethod enum (NackRequeue, NackDiscard, NackDelay) and propagate it through each middleware adapter (AMQP, Kafka, etc.) mapping onto transport-specific semantics.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=8681
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":7,"issue_count":36,"has_workaround":False,"prod_signal_quote":"I would like to be able to choose the Nack method used depending on the message processing.","has_prod_signal":False,"gap_desc":"Watermill hardcodes nack semantics; per-message Nack method (requeue/discard/delay) not supported"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Each Pub/Sub backend has different nack semantics; abstracting requires adapter changes","target_approach_file":"message.go and middleware adapters"}),
  json.dumps({"cve_id":None,"has_prod_signal":False,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":[],"maintainer_responses":[]}),
))

# 8683 — Integration with go cloud pubsub
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='issue',
  title='Add go cloud Development Kit pubsub adapter for Watermill',
  description='Add an adapter so Watermill can use the gocloud.dev pubsub abstraction, letting users reuse AWS/GCP/Azure implementations without writing their own.',
  impl_hint='Implement a go-cloud pubsub backend for Watermill following the pub-sub-implementing guide. Most work is wrapping topic/subscription lifecycle.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=8683
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":4,"issue_count":23,"has_workaround":False,"prod_signal_quote":"This would prevent us writing our own implementation for AWS and Azure ourselves, and leverage the power of the CDK","has_prod_signal":False,"gap_desc":"Watermill lacks an adapter to gocloud.dev pubsub, so users must hand-roll cloud-broker integrations"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Adapt gocloud Topic/Subscription lifecycle to Watermill Publisher/Subscriber semantics","target_approach_file":"_examples/internal-pub-sub/gocloud/"}),
  json.dumps({"cve_id":None,"has_prod_signal":False,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":["help wanted"],"maintainer_responses":[{"author_association":"MAINTAINER","body_quote":"Sounds good for me. If someone is interested with implementation, here is guide how to approach it: https://watermill.io/docs/pub-sub-implementing/"}]}),
))

# 8687 — nsq.io pub/sub
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='issue',
  title='Add NSQ Pub/Sub implementation for Watermill',
  description='Implement an NSQ (https://nsq.io/) Pub/Sub for Watermill. Maintainer has not commented in the issue.',
  impl_hint='Implement using go-nsq (https://github.com/nsqio/go-nsq). Map Producer.Publish to NSQ Publish, and Consumer.Consume to NSQ Consumer.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=8687
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":2,"issue_count":19,"has_workaround":False,"prod_signal_quote":"","has_prod_signal":False,"gap_desc":"Watermill lacks an NSQ adapter; users would have to implement it themselves"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Standard Pub/Sub adapter pattern; NSQ is simple so adapter should be small","target_approach_file":"_examples/internal-pub-sub/nsq/"}),
  json.dumps({"cve_id":None,"has_prod_signal":False,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":[],"maintainer_responses":[]}),
))

# 8688 — batch consume messages
cur.execute("""
UPDATE opportunities SET
  status='open',
  source_type='issue',
  title='Support batch message consumption in handlers',
  description='User requests a batch consumption mode for handlers so multiple messages can be processed together, reducing per-message overhead.',
  impl_hint='Add a batched handler signature (e.g. HandlerFuncBatch) or a WithBatch(size) option on handler registration. Implement at the router level so all backends benefit.',
  value_evidence=? ,
  difficulty_evidence=? ,
  urgency_evidence=? ,
  maintainer_evidence=? ,
  value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
WHERE id=8688
""", (
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"peer_impl_urls":[],"issue_reactions":2,"issue_count":26,"has_workaround":False,"prod_signal_quote":"Maybe add an batch option on adding handler","has_prod_signal":True,"gap_desc":"Watermill handlers process one message at a time; no batch consumption API"}),
  json.dumps({"canonical_impl_url":"","canonical_impl_loc":0,"why_hard":"Affects router, ack/nack semantics, and per-backend adapter code","target_approach_file":"router.go and middleware/"}),
  json.dumps({"cve_id":None,"has_prod_signal":True,"has_workaround":False}),
  json.dumps({"similar_prs":[],"welcome_labels":[],"maintainer_responses":[]}),
))

# mark task 1537 done + project active
cur.execute("UPDATE tasks SET status='done', finished_at=? WHERE id=1537", (NOW,))
cur.execute("UPDATE projects SET status='active' WHERE id='ThreeDotsLabs/watermill' AND status='analyzing'")

conn.commit()
print("watermill updates committed")
print("rows updated for watermill:")
for row in cur.execute("SELECT id, status, source_type FROM opportunities WHERE id IN (8682,8685,8689,3288,3290,8680,8681,8683,8687,8688)"):
    print(row)