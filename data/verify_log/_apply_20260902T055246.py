#!/usr/bin/env python3
"""Apply final verdicts to DB and write pending JSON."""
import json
import os
import sqlite3

DB = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"

# Final verdicts
VERDICTS = [
    {
        "opportunity_id": 319,
        "verdict": "confirmed",
        "reason": "cadence issue #3914 state=open，labels 仅 customer/wishlist/needs-info 无 wontfix，timeline 无 cross-referenced merged PR，v3 evidence 残缺但 prod_signal_quote 与 maintainer 参与讨论均成立，按硬性纪律保留",
        "checks": ["issue_state:open", "labels:[customer,wishlist,needs-info]", "timeline:no_linked_merged_pr"],
        "corrections": [],
        "degraded": False,
    },
    {
        "opportunity_id": 320,
        "verdict": "confirmed",
        "reason": "cadence issue #348 state=open，labels 无 wontfix，similar_prs (7941/7840/7799 等) 均为 worker timer/redundancy 等无关 PR，未实现 HTTP interface 功能",
        "checks": ["issue_state:open", "similar_pr_7941:merged=True:无关", "similar_pr_7840:merged=True:无关", "similar_pr_7799:merged=True:无关"],
        "corrections": [],
        "degraded": False,
    },
    {
        "opportunity_id": 4937,
        "verdict": "confirmed",
        "reason": "cadence issue #3914 v3 版，state=open，gap_desc 含 prod_signal_quote 与 maintainer MEMBER 讨论证据完整，按硬性纪律保留",
        "checks": ["issue_state:open", "evidence_complete", "maintainer_engaged"],
        "corrections": [],
        "degraded": False,
    },
    {
        "opportunity_id": 4939,
        "verdict": "confirmed",
        "reason": "cadence issue #348 v3 版，state=open，prod_signal_quote 给出 .NET 真实用户场景，gap_desc 完整；similar_prs 与 HTTP interface 无关",
        "checks": ["issue_state:open", "evidence_complete", "no_direct_implementation_pr"],
        "corrections": [],
        "degraded": False,
    },
    {
        "opportunity_id": 384,
        "verdict": "confirmed",
        "reason": "bullmq issue #862 'Find jobs by data' state=open，labels 空，无 wontfix；v2 时期 evidence 残缺但 issue 仍 open，按硬性纪律保留",
        "checks": ["issue_state:open", "labels:[]"],
        "corrections": [],
        "degraded": False,
    },
    {
        "opportunity_id": 385,
        "verdict": "confirmed",
        "reason": "bullmq issue #1040 state=open，labels=[PRO] 无 wontfix；source_type 标记为 security 但标题为 'Sequential execution' 功能请求，属于上游类型误标，非硬性反驳范畴",
        "checks": ["issue_state:open", "labels:[PRO]"],
        "corrections": [],
        "degraded": False,
    },
    {
        "opportunity_id": 386,
        "verdict": "confirmed",
        "reason": "bullmq issue #3516 '[Bug] Scheduled jobs queue randomly stop running' state=open，labels=[bug] 无 wontfix；v2 evidence 残缺但 issue 仍 open，按硬性纪律保留",
        "checks": ["issue_state:open", "labels:[bug]"],
        "corrections": [],
        "degraded": False,
    },
    {
        "opportunity_id": 5491,
        "verdict": "confirmed",
        "reason": "bullmq issue #2490 'Migrate from ioredis to node-redis' state=open，25 reactions，labels 无 wontfix；v3 evidence 自述 ioredis 维护已恢复降低 urgency，但 issue 仍 open 保留为低优机会点",
        "checks": ["issue_state:open", "reactions:25"],
        "corrections": [],
        "degraded": False,
    },
    {
        "opportunity_id": 5493,
        "verdict": "refuted",
        "reason": "bullmq issue #4211 state=closed，API 复核确认已关闭，机会点不再成立",
        "checks": ["issue_state:closed"],
        "corrections": [],
        "degraded": False,
    },
    {
        "opportunity_id": 6223,
        "verdict": "confirmed",
        "reason": "coai issue #320 'PDF images base64 占用大量 token' state=open，labels=[bug]，prod_signal_quote 含 128k vs 180k tokens 实际错误；canonical_url 空但 source_type=issue 不触发 empty-canonical 标准",
        "checks": ["issue_state:open", "labels:[bug]", "prod_signal_quote_present"],
        "corrections": [],
        "degraded": False,
    },
]

# Apply to DB
conn = sqlite3.connect(DB)
cur = conn.cursor()
for v in VERDICTS:
    oid = v["opportunity_id"]
    if v["verdict"] == "refuted":
        cur.execute("UPDATE opportunities SET status='refuted' WHERE id=?", (oid,))
        print(f"id={oid} → refuted")
    elif v["verdict"] == "corrected":
        # not used in this batch
        cur.execute("UPDATE opportunities SET status='verified' WHERE id=?", (oid,))
        print(f"id={oid} → verified (corrected)")
    else:
        cur.execute("UPDATE opportunities SET status='verified' WHERE id=?", (oid,))
        print(f"id={oid} → verified")
conn.commit()
conn.close()

# Write pending JSON
out_path = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/verify_log/.pending_20260902T055246.json"
with open(out_path, "w") as f:
    json.dump(VERDICTS, f, ensure_ascii=False, indent=2)
print(f"\nWrote pending JSON to {out_path}")
print(f"Total verdicts: {len(VERDICTS)}")