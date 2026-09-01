#!/usr/bin/env python3
"""Apply Stage 4 v2 batch judgment for tasks 1395/1396/1407 (date 2026-08-31)."""
import json
import sqlite3
from datetime import datetime, timezone

DB = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")


def ve(**kw):
    """Build a value_evidence dict with all required keys."""
    base = {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "peer_impl_urls": [],
        "issue_reactions": 0,
        "issue_count": 0,
        "has_workaround": False,
        "prod_signal_quote": "",
        "has_prod_signal": False,
        "gap_desc": "",
    }
    base.update(kw)
    return base


def de(**kw):
    base = {
        "canonical_impl_url": "",
        "canonical_impl_loc": 0,
        "why_hard": "",
        "target_approach_file": "",
    }
    base.update(kw)
    return base


def ue(**kw):
    base = {"cve_id": None, "has_prod_signal": False, "has_workaround": False}
    base.update(kw)
    return base


def me(**kw):
    base = {"similar_prs": [], "maintainer_responses": [], "welcome_labels": []}
    base.update(kw)
    return base


# ---------- Task 1395: rulego/rulego ----------
# 1977 (本地缓存建议三个返回链路) - 0/0 reactions, vague API design suggestion -> DELETE
# 8314 ([需求收集]) - meta-discussion bucket -> DELETE
# 8313 (Seeking Collaborators) - meta-discussion -> DELETE
# KEEP: 1983 (非DSL支持手动设置node id) and 8317 (dbClient batch insert) - both actionable
ACTIONS = {
    1983: {
        "source_type": "issue",
        "title": "非DSL方式支持手动设置node的id",
        "description": "用户希望不通过DSL即可手动设置RuleGo rule chain节点的id，便于其他节点ref引用。当前仅DSL方式支持设置节点id。",
        "impl_hint": "在 RuleContext/RuleNode 构造器或 builder API 中暴露 SetId/WithId 方法，并在 ChainBuilder.Register 时跳过id自动生成逻辑；保留 DSL JSON 解析路径的兼容。",
        "value_evidence": ve(issue_count=1, gap_desc="RuleGo chain 仅DSL方式可指定节点id，编程式构造API无法手动设定id，导致外部节点ref引用困难。"),
        "difficulty_evidence": de(why_hard="改动 chain builder 与 node registry 内部 id 生成逻辑，需要保证 DSL 路径与编程路径互不破坏；改动面较小但需新增 API。"),
        "urgency_evidence": ue(),
        "maintainer_evidence": me(),
    },
    8317: {
        "source_type": "issue",
        "title": "[dbClient] node supports batch insert",
        "description": "RuleGo 的 dbClient 节点目前仅支持单条 insert，需要补充批量插入能力以减少数据库往返、提升吞吐。",
        "impl_hint": "在 components/db/dbclient.go 的 Insert 方法旁新增 BatchInsert(items []map[string]any) 接口，按目标方言（MySQL/PostgreSQL/SQLite）拼占位符与事务；保留原 Insert 的兼容路径。",
        "value_evidence": ve(gap_desc="dbClient 节点无批量插入接口，多条记录必须循环单条 insert，吞吐量与事务一致性较差。"),
        "difficulty_evidence": de(why_hard="需跨多种 SQL 方言实现批量插入与事务封装，并保持与现有单条 insert 接口行为一致。"),
        "urgency_evidence": ue(),
        "maintainer_evidence": me(),
    },

    # ---------- Task 1396: zenstackhq/zenstack ----------
    # 8310 (zod omit fields), 8311 (LSP standalone), 8312 (IntelliJ plugin), 5612 (@@allow anon warning), 8305 (@createdBy/@updatedBy) -> DELETE: feature requests, no canonical, low specificity or scope-discussion
    # KEEP: 8307 (Migrations API), 8303 (MCP schema), 8304 (multi-protocol generate), 8306 (test mocks/seeds), 8309 (transitive import - confirmed open and maintainer acknowledged)
    8307: {
        "source_type": "issue",
        "title": "Provide Migrations API",
        "description": "Prisma 本身不暴露 migrations 的程序化调用（参见 prisma/prisma#4703）。ZenStack 缺乏迁移 API，用户只能通过 shell exec 调用 prisma migrate 命令，不利于在 CI/无 shell 环境中运行迁移。",
        "impl_hint": "在 @zenstackhq/orm 或独立子包中暴露 runMigrate / generateMigration / applyMigration API，对接 prisma migrate 的内部引擎（Node API 或 CLI 子进程封装），并与 access policy、enhance 流程串联。",
        "value_evidence": ve(
            issue_reactions=3, issue_count=34, has_workaround=True, has_prod_signal=True,
            prod_signal_quote="still manually create my own API routes using tRPC for instance, and calling the enhance() function. But for developer productivity, it would be nice if this versioning could be handled for me, since ZenStack knows about my schema and it knows about versioning.",
            gap_desc="ZenStack 缺少程序化迁移 API，依赖 prisma CLI 的 shell exec；维护者表示与核心功能（access policy）集成时才会考虑。"),
        "difficulty_evidence": de(why_hard="需封装 Prisma 内部迁移引擎并与 ZenStack 的 schema pipeline、access policy 集成；涉及 CLI 调用或内部 Node API 包装。"),
        "urgency_evidence": ue(has_prod_signal=True, has_workaround=True),
        "maintainer_evidence": me(
            similar_prs=[
                {"number": 2599, "title": "merge dev to main (v3.6.1)", "merged": True, "url": "https://github.com/zenstackhq/zenstack/pull/2599", "age_days": 131, "maintainer_comment": ""},
                {"number": 2676, "title": "feat(orm): implement delegateMap attribute", "merged": True, "url": "https://github.com/zenstackhq/zenstack/pull/2676", "age_days": 102, "maintainer_comment": ""},
                {"number": 2573, "title": "feat(orm): add fuzzy search and relevance ordering (PostgreSQL)", "merged": True, "url": "https://github.com/zenstackhq/zenstack/pull/2573", "age_days": 142, "maintainer_comment": ""},
            ],
            maintainer_responses=[{"body_quote": "Hi @tylergets, ZenStack doesn't integrate with Prisma migrate in any way today. If it does that I think it should do it in a way that's integrated with other core features (access control etc.)."}]),
    },
    8303: {
        "source_type": "issue",
        "title": "Optimized Schema Generation for MCP Servers",
        "description": "ZenStack 当前为 MCP server 生成的 schema 体积过大，超出 MCP 上下文窗口；用户希望提供可配置深度/裁剪的 schema 生成选项，使大型数据库 schema 也能接入 MCP server。",
        "impl_hint": "在 @zenstackhq/schema 或 CLI 的 generate 子命令中新增 --depth / --include / --exclude 选项，允许按 model/relation 裁剪生成的 schema；为 MCP server adapter 提供 slim 模式。",
        "value_evidence": ve(
            issue_reactions=7, issue_count=36, has_workaround=True, has_prod_signal=True,
            prod_signal_quote="Enable developers with large or complex schemas to actually use ZenStack-powered MCP servers in production. Issue: ZenStack-generated schemas are too large for MCP context limits when working with big databases",
            gap_desc="ZenStack schema 生成器对大型 schema 输出过大，触发 MCP 上下文限制；维护者表示原本的 configurable depth 只是 workaround，需根本性重做。"),
        "difficulty_evidence": de(why_hard="涉及 schema 生成器遍历逻辑与关系深度裁剪，需重新设计而非简单加 flag；需要与 MCP server adapter 联动。"),
        "urgency_evidence": ue(has_prod_signal=True, has_workaround=True),
        "maintainer_evidence": me(
            maintainer_responses=[
                {"body_quote": "@baenio, First, I want to thank you for taking the time to test it with your real case and for providing such a detailed investigation and feasible request. I'm really sorry it didn't work out."},
                {"body_quote": "@baenio Sorry for the delay. I've been thinking this over, and honestly, the original plan for 'Configurable schema depth' was really just a workaround."},
            ]),
    },
    8304: {
        "source_type": "issue",
        "title": "Generate RESTful, GraphQL and tRPC at the same time",
        "description": "用户希望 ZenStack 能在同一个 schema 上同时生成 REST、GraphQL 和 tRPC 三种 server adapter，避免为同一数据模型维护多个独立的生成器。",
        "impl_hint": "在 @zenstackhq/cli 的 generate 流程中允许通过单一配置文件（如 zenstack.config.ts）声明多个 server adapter 列表（trpc + rest + graphql），按顺序对增强 client 应用所有 generator。",
        "value_evidence": ve(
            issue_reactions=6, issue_count=29, has_workaround=False, has_prod_signal=True,
            prod_signal_quote="We are using ZenStack in production along with GraphQL using NestJS. We combine the ZenStack enhanced client, Unlight/Prisma-NestJS-GraphQL, and a custom p",
            gap_desc="ZenStack 当前需为不同 server adapter 多次 generate，生产用户需手动组合多套生成器；维护者表示 tRPC/GraphQL 已支持但缺少统一编排。"),
        "difficulty_evidence": de(why_hard="需抽象 server adapter 注册机制并支持多 adapter 并存；需考虑各 adapter 的 plugin lifecycle 与冲突解决。"),
        "urgency_evidence": ue(has_prod_signal=True, has_workaround=False),
        "maintainer_evidence": me(
            maintainer_responses=[{"body_quote": "Hey @olehmelnyk, today you can already use the trpc plugin to generate trpc routers. For REST, you can simply use one of the supported server adapters to install automatic APIs to the server, no code"}]),
    },
    8306: {
        "source_type": "issue",
        "title": "Generate test mocks / DB seeds",
        "description": "用户希望 ZenStack 能基于 ZModel schema 自动生成测试 mock 与 DB seed 数据（含姓名/邮箱/图片/日期等映射），方便测试环境构造数据。",
        "impl_hint": "新增 plugin：基于 schema 类型生成 fakerjs 风格的 mock 工厂（@zenstackhq/plugin-mock），支持 per-field 策略覆盖，输出可注入 Prisma client 的 seed 脚本。",
        "value_evidence": ve(
            issue_reactions=3, issue_count=31, has_workaround=False,
            gap_desc="ZenStack 缺少从 ZModel 自动生成测试 mock/seed 的能力，用户需手写或依赖第三方 faker 库。"),
        "difficulty_evidence": de(why_hard="需遍历 ZModel 关系生成符合外键约束与字段类型的 mock 数据，复杂度集中在 relation 拓扑排序。"),
        "urgency_evidence": ue(),
        "maintainer_evidence": me(
            similar_prs=[
                {"number": 2113, "title": "merge dev to main (v2.14.2)", "merged": True, "url": "https://github.com/zenstackhq/zenstack/pull/2113", "age_days": 480, "maintainer_comment": ""},
                {"number": 1767, "title": "fix(hooks): support optimistic update for 'upsert'", "merged": True, "url": "https://github.com/zenstackhq/zenstack/pull/1767", "age_days": 691, "maintainer_comment": ""},
            ],
            maintainer_responses=[{"body_quote": "Hi @olehmelnyk, it's a great idea. Right now, the focus of ZenStack is still on the core runtime and integrations with major frameworks, but I do see this as a great match for a community-contributed"}]),
    },
    8309: {
        "source_type": "issue",
        "title": "Transitive import (barrel files)",
        "description": "ZenStack 当前不支持 .zmodel 文件从其他 barrel/index 文件间接导入 schema；维护者后续回复承认应支持，但 issue 仍 open。",
        "impl_hint": "在 @zenstackhq/language 解析器中扩展 module loader：对 `import './xxx'` 路径做递归展开，构建完整 schema 关系图，循环引用时给出明确错误。",
        "value_evidence": ve(
            issue_reactions=2, issue_count=19, has_workaround=False,
            gap_desc="ZModel 间接 import 不被支持，大型项目难以模块化组织 schema。"),
        "difficulty_evidence": de(why_hard="需修改 ZModel 解析器模块加载逻辑，处理递归展开与循环引用检测。"),
        "urgency_evidence": ue(),
        "maintainer_evidence": me(
            similar_prs=[
                {"number": 2775, "title": "feat(cli): add --introspect option for studio command for bootstrapping without schema", "merged": True, "url": "https://github.com/zenstackhq/zenstack/pull/2775", "age_days": 32, "maintainer_comment": ""},
                {"number": 1082, "title": "fix: clean up generation of logical prisma client", "merged": True, "url": "https://github.com/zenstackhq/zenstack/pull/1082", "age_days": 908, "maintainer_comment": ""},
            ],
            maintainer_responses=[
                {"body_quote": "@platon-ivanov, It is already supported. Have you seen any issue with it?"},
                {"body_quote": "Sorry that I missed the tittle, thought it just for nested imported. I agree it's something we should support."},
            ]),
    },

    # ---------- Task 1407: astronomer/astronomer-cosmos ----------
    # 7229 (compatibility/issue:1683) - keep: real bug with prod signal
    # 8324 (compatibility/issue:1443) - keep: real feature request with maintainer discussion
    # 2193 (issue/issue:1416) - DELETE: pure feature request question, low reactions, no prod signal
    # 7226 (issue/issue:902) - DELETE: write-audit-publish is design discussion, not actionable
    # 7227 (issue/issue:2329) - keep: concrete feature with maintainer intent
    # 7228 (issue/issue:679) - keep: install_deps KUBERNETES feature parity
    # 7225 (performance/issue:2294) - keep: real perf issue with reactions and merged PRs
    # 8321 (performance/issue:764) - DELETE: long-running design discussion, no concrete scope
    7229: {
        "source_type": "compatibility",
        "title": "[Bug] WITH_TESTS_OR_FRESHNESS is not working properly with TestBehavior.BUILD",
        "description": "Cosmos 1.9.0 + dbt-core 1.9.2 + dbt-bigquery 1.9.1 + Airflow 2.10.2，LoadMode=DBT_LS_MANIFEST，InvocationMode=DBT_RUNNER，TestBehavior.BUILD 模式下 source tests 实际未被运行（prod 环境 Google Cloud Composer）。",
        "impl_hint": "定位 cosmos/providers/dbt/cloud/bigquery.py 与 cosmos/operators/_graph_operators.py 中 TestBehavior.BUILD 分支，确认 source_rendering 与 freshness 任务未正确加入 DAG task 列表；参考 cosmos/issues/764 与 pr/2428 已有讨论。",
        "value_evidence": ve(
            issue_reactions=1, issue_count=30, has_workaround=False, has_prod_signal=True,
            prod_signal_quote="We hit this in production with Google Cloud Composer; TestBehavior.BUILD because as of now source tests is never run.",
            gap_desc="Cosmos 的 TestBehavior.BUILD 模式下 source/freshness 测试未触发，与 dbt-core 自身 dbt build 行为不一致。"),
        "difficulty_evidence": de(why_hard="涉及 Airflow DAG 任务构建与 dbt invocation mode 的耦合，需要在 DBT_RUNNER/DBT_LS_MANIFEST 两条路径上对齐；已有相关 PR #2428 提供思路。"),
        "urgency_evidence": ue(has_prod_signal=True, has_workaround=False),
        "maintainer_evidence": me(similar_prs=[
            {"number": 2428, "title": "override the build command and use run when watcher execution test behavior is set to NONE or AFTER_ALL", "merged": False, "url": "https://github.com/astronomer/astronomer-cosmos/pull/2428", "age_days": 180, "maintainer_comment": ""},
        ], welcome_labels=[]),
    },
    # 8324 (issue:1443) is in DELETE_IDS (duplicate of already-open 2192).
    7227: {
        "source_type": "issue",
        "title": "Support emitting Airflow assets/datasets with ExecutionMode.KUBERNETES",
        "description": "Cosmos 当前仅 LOCAL/VIRTUALENV/WATCHER 三种 ExecutionMode 支持发出 Airflow datasets（AF2）/ aliases（AF3），KUBERNETES 模式不支持，导致 pod-based 执行无法接入数据血缘。",
        "impl_hint": "在 cosmos/operators/_dag_builder.py 的 KUBERNETES 分支中补齐 outlets 字段生成逻辑，复用 WATCHER 已有的 dataset 注入代码（参考 PR #2595）。",
        "value_evidence": ve(
            issue_reactions=2, issue_count=28, has_workaround=False, has_prod_signal=True,
            prod_signal_quote="support emitting datasets also for modes KUBERNETES and WATCHER_KUBERNETES (assets emitted by the watchers, not the producer). This would also make it usable by other pod-based execution modes.",
            gap_desc="Cosmos 的 KUBERNETES ExecutionMode 不输出 Airflow assets/datasets，与 LOCAL/VIRTUALENV/WATCHER 行为不一致。"),
        "difficulty_evidence": de(why_hard="需要在 KubernetesPodOperator 任务构造时为 outlets 字段写入 dataset URI，涉及 DAG 序列化与 pod 模板之间的耦合。"),
        "urgency_evidence": ue(has_prod_signal=True, has_workaround=False),
        "maintainer_evidence": me(similar_prs=[
            {"number": 2595, "title": "Emit per-model outlets in ExecutionMode.WATCHER_KUBERNETES", "merged": True, "url": "https://github.com/astronomer/astronomer-cosmos/pull/2595", "age_days": 130, "maintainer_comment": ""},
            {"number": 2755, "title": "Add configurable seed rendering behavior", "merged": True, "url": "https://github.com/astronomer/astronomer-cosmos/pull/2755", "age_days": 89, "maintainer_comment": ""},
            {"number": 2207, "title": "Introduce ExecutionMode.WATCHER_KUBERNETES to use watcher with KubernetesPodOperator", "merged": True, "url": "https://github.com/astronomer/astronomer-cosmos/pull/2207", "age_days": 257, "maintainer_comment": ""},
        ]),
    },
    7228: {
        "source_type": "issue",
        "title": "Support installing dbt dependencies when using ExecutionMode.KUBERNETES",
        "description": "Cosmos 在 LOCAL/VIRTUALENV 下支持 install_deps=True 安装 dbt deps，但 KUBERNETES 模式不支持；K8s 容器镜像未包含完整依赖时需要该特性。",
        "impl_hint": "在 cosmos/operators/_dag_builder.py 的 KUBERNETES 分支中添加 init container 或 task-level step 调用 dbt deps；保持 install_deps 语义一致。",
        "value_evidence": ve(
            issue_reactions=1, issue_count=29, has_workaround=False,
            gap_desc="Cosmos KUBERNETES ExecutionMode 缺失 install_deps 支持，与 LOCAL/VIRTUALENV 行为不一致。"),
        "difficulty_evidence": de(why_hard="需要在 K8s pod 模板中插入 dbt deps 执行步骤，并处理好镜像构建与依赖缓存的生命周期。"),
        "urgency_evidence": ue(),
        "maintainer_evidence": me(similar_prs=[
            {"number": 2939, "title": "Raise minimum supported dbt-core version to 1.8", "merged": True, "url": "https://github.com/astronomer/astronomer-cosmos/pull/2939", "age_days": 31, "maintainer_comment": ""},
            {"number": 2773, "title": "Add dbt-core 1.12 to test matrix", "merged": True, "url": "https://github.com/astronomer/astronomer-cosmos/pull/2773", "age_days": 87, "maintainer_comment": ""},
        ], maintainer_responses=[{"body_quote": "@MrBones757 I believe there would be two motivations for this implementation: 1. Feature parity 2. In case the container images don't contain the dbt project."}]),
    },
    7225: {
        "source_type": "performance",
        "title": "Optimize manifest loading for DAGs with multiple DbtTaskGroups",
        "description": "Cosmos 在 LoadMode.DBT_MANIFEST 下每次构造 DbtTaskGroup/DbtDag 都会全量读+解析 manifest.json；KubernetesExecutor 下每个 worker pod 都要为每个 DbtTaskGroup 重新解析，DAG 任务图启动成本随 TaskGroup 数线性放大。",
        "impl_hint": "为 manifest.json 引入进程级或 worker 级的 LRU 缓存（参考 PR #1014 的 dbt ls 缓存方案），并在 LoadMode 中新增 CACHED_MANIFEST 选项。",
        "value_evidence": ve(
            issue_reactions=4, issue_count=29, has_workaround=False,
            gap_desc="Cosmos 在 DBT_MANIFEST 模式下重复解析 manifest，K8s executor 环境下每个 worker 都要 N×M 次解析。"),
        "difficulty_evidence": de(why_hard="需要在 DAG 序列化层与 K8s executor 之间设计共享缓存，并考虑 invalidation 与并发安全。"),
        "urgency_evidence": ue(),
        "maintainer_evidence": me(similar_prs=[
            {"number": 576, "title": "Ensure filtering with manifest loading works with single model", "merged": True, "url": "https://github.com/astronomer/astronomer-cosmos/pull/576", "age_days": 1060, "maintainer_comment": ""},
            {"number": 2432, "title": "cache manifest file", "merged": False, "url": "https://github.com/astronomer/astronomer-cosmos/pull/2432", "age_days": 179, "maintainer_comment": ""},
        ], maintainer_responses=[{"body_quote": "@ferjanin, some time ago, we introduced an approach towards caching dbt ls output to avoid the full reparse when using that load mode: https://github.com/astronomer/astronomer-cosmos/pull/1014"}]),
    },
}

# IDs to DELETE (draft -> draft removed)
DELETE_IDS = [
    1977,  # rulego:104 - vague API design suggestion, 0 reactions
    8314,  # rulego:26 - meta-discussion bucket
    8313,  # rulego:27 - seeking collaborators (meta)
    2193,  # cosmos:1416 - question/feature request, no prod signal, no concrete scope
    7226,  # cosmos:902 - write-audit-publish design discussion
    8321,  # cosmos:764 - long-running design discussion
    8310,  # zenstack:2201 - small inconsistency, low value
    8311,  # zenstack:1156 - LSP standalone, vague scope
    8312,  # zenstack:2360 - IntelliJ plugin bug, low priority
    5612,  # zenstack:397 - @@allow anon warning, design-level
    8305,  # zenstack:1505 - @createdBy/@updatedBy, scope discussion
    8324,  # cosmos:1443 - duplicate of already-open 2192
]

TASK_DONE = [1395, 1396, 1407]


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    # Updates
    for oid, a in ACTIONS.items():
        cur.execute(
            """UPDATE opportunities
               SET status='open',
                   source_type=?, title=?, description=?, impl_hint=?,
                   value_evidence=?, difficulty_evidence=?, urgency_evidence=?, maintainer_evidence=?,
                   value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
               WHERE id=?""",
            (a["source_type"], a["title"], a["description"], a["impl_hint"],
             json.dumps(a["value_evidence"]), json.dumps(a["difficulty_evidence"]),
             json.dumps(a["urgency_evidence"]), json.dumps(a["maintainer_evidence"]),
             oid),
        )
        print(f"open  {oid} -> {a['source_type']}: {a['title']}")
    # Deletes
    for oid in DELETE_IDS:
        cur.execute("DELETE FROM opportunities WHERE id=?", (oid,))
        print(f"del   {oid}")
    # Mark tasks done
    for tid in TASK_DONE:
        cur.execute(
            "UPDATE tasks SET status='done', finished_at=? WHERE id=? AND status<>'done'",
            (NOW, tid),
        )
        print(f"task  {tid} -> done")
    # Promote projects
    for proj_id in ("astronomer/astronomer-cosmos", "rulego/rulego", "zenstackhq/zenstack"):
        cur.execute(
            "UPDATE projects SET status='active' WHERE id=? AND status='analyzing'",
            (proj_id,),
        )
        print(f"proj  {proj_id} -> active")
    conn.commit()
    conn.close()
    print("OK")


if __name__ == "__main__":
    main()