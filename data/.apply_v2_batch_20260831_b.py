#!/usr/bin/env python3
"""Stage 4 v2 batch judgment for tasks 1424/1425/1426 (date 2026-08-31)."""
import json
import sqlite3
from datetime import datetime, timezone

DB = "/Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline/data/pipeline.db"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

conn = sqlite3.connect(DB)
c = conn.cursor()


def ve(**kw):
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
    base = {"canonical_impl_url": "", "canonical_impl_loc": 0, "why_hard": "", "target_approach_file": ""}
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


# ============ Task 1424 (mobxjs/mobx-state-tree) ============
# ALL drafts DELETE: every draft is missing canonical_url; gap_desc for 5274/8366/8367 contains "RFC" meta-discussion.
# No canonical reference + RFC meta-discussion → DELETE
c.execute("DELETE FROM opportunities WHERE task_id=1424")
c.execute(
    "UPDATE tasks SET status='done', finished_at=? WHERE id=1424",
    (NOW,),
)
c.execute(
    "UPDATE projects SET status='active' WHERE id='mobxjs/mobx-state-tree' AND status='analyzing'"
)


# ============ Task 1425 (nats-io/nats.java) ============
# 2573 (feature_gap:encoders) DELETE: Java has Encoding.java/JsonSerializable/JsonParser under different naming
# 8383 (feature_gap:Makefile) DELETE: build config / dotfile-meta blacklisted
# 8384 (feature_gap:bench) DELETE: target_has_stub=true (AutoBenchmark.java already exists)
# 8386 (feature_gap:internal) DELETE: implementation-detail dir, not a user-facing feature
# 2576 (issue:1576) OPEN: JetStream pull subscription high-cardinality hang with prod signal

c.execute("DELETE FROM opportunities WHERE id IN (2573,8383,8384,8386)")

c.execute(
    """UPDATE opportunities SET
        status='open',
        source_type='issue',
        title='NatsJetStreamPullSubscription.iterate() can block far beyond maxWait under high subject cardinality',
        description='nats.java 的 JetStream 拉取消费 iterate() 在高 subject cardinality 场景下静默阻塞，超过 maxWait；服务端 nats consumer report 显示无活动消息但 Java 客户端继续等待。',
        impl_hint='在 NatsJetStreamPullSubscription.iterate() 中加入无 pull_pending 反馈时的超时/心跳检测；当服务端连续多次 pull 请求都返回 408/无消息时应唤醒 consumer；参考 nats.go 的 jetstream pull consumer 在超时与空批次场景下的处理。',
        value_evidence=?, difficulty_evidence=?, urgency_evidence=?, maintainer_evidence=?,
        value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
    WHERE id=2576""",
    (
        json.dumps(ve(
            canonical_impl_url="https://github.com/nats-io/nats.go/tree/main/jetstream",
            peer_impl_urls=[],
            issue_reactions=0, issue_count=3, has_workaround=True,
            has_prod_signal=True,
            prod_signal_quote="After hours-to-days of healthy operation, the consume loop silently stops making progress. No exception, no onError, no log. Server-side nats consumer report shows no activity",
            gap_desc="nats.java 的 JetStream pull subscription iterate() 在高 cardinality 场景下静默 hang，需增加空批次/超时唤醒机制。",
        )),
        json.dumps(de(
            canonical_impl_url="https://github.com/nats-io/nats.go/tree/main/jetstream",
            why_hard="需在 pull request 流程中加入 408/空批次的超时唤醒逻辑，涉及连接状态与 JetStream API 响应处理。",
            target_approach_file="src/main/java/io/nats/client/NatsJetStreamPullSubscription.java",
        )),
        json.dumps(ue(has_prod_signal=True, has_workaround=True)),
        json.dumps(me()),
    ),
)
c.execute(
    "UPDATE tasks SET status='done', finished_at=? WHERE id=1425",
    (NOW,),
)
c.execute(
    "UPDATE projects SET status='active' WHERE id='nats-io/nats.java' AND status='analyzing'"
)


# ============ Task 1426 (tortoise/aerich) ============
# 4046 (149 on_delete): duplicate of 8382 (538) → DELETE
# 8378 (192 asyncpg pool error): old aerich 0.5.7, low signal → DELETE
# 8379 (254 Guide integration): documentation request, not a contribution opportunity → DELETE
# Other 7 drafts → OPEN

c.execute("DELETE FROM opportunities WHERE id IN (4046,8378,8379)")

OPEN_AERICH = {
    8373: dict(
        source_type="compatibility",
        title="Support datamigrations (programmatic migration logic in Python, not only SQL)",
        description="aerich 当前仅生成 SQL 迁移文件，而 Django/alembic 支持 Python 脚本编写数据迁移逻辑；维护者已表示会考虑该功能。",
        impl_hint="在 aerich migrate 流程中增加可选 Python 迁移脚本执行路径：扫描 migrations/<app>/<version>.py 的 upgrade/downgrade，与现有 SQL 迁移并存；在 tortoise migrate runner 串联两步。",
        ve=ve(
            peer_impl_urls=["https://github.com/sqlalchemy/alembic"],
            issue_reactions=8, issue_count=1, has_workaround=False,
            has_prod_signal=True,
            prod_signal_quote="I mean when you can write your migration logic in python, not only SQL. Django and alembic support them, but aerich not :(",
            gap_desc="aerich 缺失 alembic/Django 风格的 Python 数据迁移能力；仅生成 SQL 迁移不足以表达复杂 backfill/business 逻辑。",
        ),
        de=de(why_hard="需在现有 SQL 迁移 pipeline 中插入 Python 脚本执行步骤，扩展 migrate runner 调度，并保持向后兼容。", target_approach_file="aerich/migrate.go"),
        ue=ue(has_prod_signal=True, has_workaround=False),
        me=me(maintainer_responses=[{"body_quote": "That'a a good feature, I will consider it"}]),
    ),
    8375: dict(
        source_type="compatibility",
        title="Support altering columns in SQLite migrations by RENAME-ADD-UPDATE-DROP",
        description="aerich 在 SQLite 下只能 drop column，不能 alter column 类型/默认值；提议按 SQLite 官方推荐做法：RENAME→ADD→UPDATE→DROP 实现无损 schema 变更。",
        impl_hint="在 aerich/ddl/sqlite.py 中扩展 alter_column 操作：生成 RENAME COLUMN + ADD COLUMN + UPDATE 拷贝 + DROP COLUMN 四步迁移脚本，参考 SQLAlchemy alembic 的 SQLite 兼容层。",
        ve=ve(
            peer_impl_urls=["https://gerrit.sqlalchemy.org/c/sqlalchemy/alembic/+/2011"],
            issue_reactions=2, issue_count=1, has_workaround=False,
            has_prod_signal=True,
            prod_signal_quote="Since 7bcf9b2fedaca4b0a7948b06daf2ff16f3fda2e3, dropping columns in SQLite migrations is possible. We may further support altering columns in SQLite by RENAME-ADD-UPDATE-DROP",
            gap_desc="aerich 在 SQLite 下的 alter column 能力缺失，用户需手工编写多步迁移绕开 SQLite ALTER COLUMN 限制。",
        ),
        de=de(why_hard="需在 SQLite DDL 生成器中正确处理 ALTER COLUMN 的多步翻译，包括类型 cast 与 NOT NULL 校验，跨版本兼容。", target_approach_file="aerich/ddl/sqlite.py"),
        ue=ue(has_prod_signal=True, has_workaround=True),
        me=me(),
    ),
    8377: dict(
        source_type="compatibility",
        title="Support per-database type subfolders under migrations/ directory",
        description="当用户在 SQLite (本地) 与 MySQL/Postgres (生产) 之间切换时，aerich 把所有 SQL 迁移放在同一目录，需要手工拷贝防覆盖；提议按方言分子目录隔离。",
        impl_hint="在 aerich migrate 命令中支持 --db-type 子目录（如 migrations/sqlite/models/0_init.sql），按当前 connection dialect 选取对应目录生成/执行；保留旧单目录路径兼容。",
        ve=ve(
            peer_impl_urls=["https://alembic.sqlalchemy.org/en/latest/cookbook.html#rudimental-schema-versioning-for-databases-that-dont-support-altering-tables"],
            issue_reactions=1, issue_count=1, has_workaround=True,
            has_prod_signal=True,
            prod_signal_quote="even though different migrations files are created for different database types, it stores them all in the same place under migrations/ and I currently have to manually copy the folder around",
            gap_desc="aerich 的 migrations/ 目录不支持按方言隔离，多数据库用户需要手工搬运迁移文件避免覆盖。",
        ),
        de=de(why_hard="需扩展 migrate 路径解析与 init 模板以支持方言子目录，兼顾多 dialect 工作流的向后兼容。", target_approach_file="aerich/migrate.go"),
        ue=ue(has_prod_signal=True, has_workaround=True),
        me=me(),
    ),
    8381: dict(
        source_type="compatibility",
        title="Cannot drop index needed in a foreign key constraint",
        description="aerich 生成的 drop index 迁移在 MySQL/Postgres 上会因 FK 约束引用而失败；用户手工改写为 drop→add unique index 才可执行。",
        impl_hint="在 aerich/ddl/{mysql,postgres}.py 的 drop index 实现中先识别外键引用，自动生成 DROP FK → DROP INDEX → ADD 索引 → ADD FK 的复合迁移。",
        ve=ve(
            issue_reactions=0, issue_count=1, has_workaround=True,
            has_prod_signal=True,
            prod_signal_quote="After doing this change, the migration works",
            gap_desc="aerich 直接生成的 DROP INDEX 在 MySQL/Postgres 上因 FK 约束失败，缺少 drop-and-rebuild 复合 DDL 生成。",
        ),
        de=de(why_hard="需解析 INDEX/FK 依赖并在 DDL 生成中插入 DROP FK + ADD FK 包装，方言差异较大。", target_approach_file="aerich/ddl/mysql.py"),
        ue=ue(has_prod_signal=True, has_workaround=True),
        me=me(),
    ),
    8382: dict(
        source_type="compatibility",
        title="on_delete change does not trigger aerich migrate to generate a migration file",
        description="Tortoise model 中将 ForeignKeyField 的 on_delete 从默认 CASCADE 改为 SET_NULL 后，运行 aerich migrate 检测不到 schema 变化（issue 538 与历史 149 同一问题）。",
        impl_hint="在 aerich/utils.py 的 model diff 计算中扩展对 ForeignKeyField.on_delete 的比对；当前可能仅看字段类型而忽略 on_delete 元数据，需在差异集合中暴露该字段。",
        ve=ve(
            issue_reactions=0, issue_count=1, has_workaround=True,
            has_prod_signal=True,
            prod_signal_quote="change ForeignKeyField default on_delete from CASCADE to SET_NULL and running aerich migrate does not generate migration file",
            gap_desc="aerich 的 model diff 未比对 ForeignKeyField.on_delete 元数据，导致 on_delete 变更不产生迁移文件。",
        ),
        de=de(why_hard="需修改 model diff 算法以追踪 ForeignKeyField 元数据子字段，确保序列化完整；需覆盖 introspection 的所有 dialect。", target_approach_file="aerich/utils.py"),
        ue=ue(has_prod_signal=True, has_workaround=True),
        me=me(),
    ),
    4048: dict(
        source_type="compatibility",
        title="Update CONSTRAINT name when table name changed",
        description="修改表名时，aerich 没有同步更新 FK constraint 名字，致 constraint 名称与表名不一致，不利于细粒度数据库管理。",
        impl_hint="在 aerich 的 rename_table 路径中遍历该表的 FK constraint，重新生成以新表名为前缀的 constraint 名并写入 ALTER TABLE 重命名语句。",
        ve=ve(
            issue_reactions=1, issue_count=1, has_workaround=False,
            has_prod_signal=True,
            prod_signal_quote="After modifying the table name, that will be great to do a CONSTRAINT name update of the relationship field along with it.",
            gap_desc="aerich 的 rename_table 未同步更新 FK constraint 名称，constraint 与新表名不一致。",
        ),
        de=de(why_hard="需在 rename_table 中重新计算并输出 CONSTRAINT 重命名语句，跨方言差异需覆盖。", target_approach_file="aerich/migrate.go"),
        ue=ue(has_prod_signal=True, has_workaround=False),
        me=me(),
    ),
    4052: dict(
        source_type="compatibility",
        title="DROP INDEX CONCURRENTLY cannot run inside a transaction block (asyncpg/Postgres)",
        description="当 aerich 的 in-transaction 标志为 false 时，asyncpg 仍报 DROP INDEX CONCURRENTLY 在事务块内错误；aerich/__init__.py:190 看似出事务但实际仍处事务。",
        impl_hint="在 aerich migrate 执行 DROP INDEX CONCURRENTLY 时强制使用 autocommit 连接，复用 tortoise-orm 的 transaction 包装逻辑绕开 asyncpg 事务约束。",
        ve=ve(
            issue_reactions=0, issue_count=1, has_workaround=False,
            has_prod_signal=True,
            prod_signal_quote="asyncpg.exceptions.ActiveSQLTransactionError: DROP INDEX CONCURRENTLY cannot run inside a transaction block",
            gap_desc="aerich 在 asyncpg/Postgres 上执行 DROP INDEX CONCURRENTLY 仍受事务块约束，与 --in-transaction false 行为不一致。",
        ),
        de=de(why_hard="需在 DDL 执行路径上区分 autocommit/transaction 模式，并修复连接池状态恢复逻辑。", target_approach_file="aerich/__init__.py"),
        ue=ue(has_prod_signal=True, has_workaround=False),
        me=me(),
    ),
}

for oid, info in OPEN_AERICH.items():
    c.execute(
        """UPDATE opportunities SET
            status='open',
            source_type=?, title=?, description=?, impl_hint=?,
            value_evidence=?, difficulty_evidence=?, urgency_evidence=?, maintainer_evidence=?,
            value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL
        WHERE id=?""",
        (
            info["source_type"], info["title"], info["description"], info["impl_hint"],
            json.dumps(info["ve"]), json.dumps(info["de"]), json.dumps(info["ue"]), json.dumps(info["me"]),
            oid,
        ),
    )

c.execute("UPDATE tasks SET status='done', finished_at=? WHERE id=1426", (NOW,))
c.execute(
    "UPDATE projects SET status='active' WHERE id='tortoise/aerich' AND status='analyzing'"
)

conn.commit()
conn.close()
print("OK: applied batch 1424/1425/1426")