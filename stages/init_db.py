#!/usr/bin/env python3
"""初始化 SQLite 数据库，创建所有表。幂等：已存在的表不会被删除。"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'pipeline.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,
    name            TEXT,
    url             TEXT,
    language        TEXT,
    stars           INTEGER,
    open_issues     INTEGER,
    last_commit_at  TEXT,
    latest_release  TEXT,
    latest_release_at TEXT,
    topics          TEXT,
    description     TEXT,
    archived        INTEGER DEFAULT 0,
    source          TEXT,
    status          TEXT DEFAULT 'discovered',
    first_seen_at   TEXT,
    prev_stars       INTEGER,
    prev_open_issues INTEGER,
    last_fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS project_meta (
    project_id      TEXT PRIMARY KEY,
    canonical_name  TEXT,
    canonical_lang  TEXT,
    canonical_url   TEXT,
    canonical_stars INTEGER,
    peer_versions   TEXT,
    filter_status   TEXT DEFAULT 'pending',
    filter_reason   TEXT,
    filtered_at     TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT,
    task_date       TEXT,
    task_type       TEXT,
    trigger_reason  TEXT,
    status          TEXT DEFAULT 'pending',
    created_at      TEXT,
    started_at      TEXT,
    finished_at     TEXT,
    UNIQUE(project_id, task_date, task_type)
);

CREATE TABLE IF NOT EXISTS analyses (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       TEXT,
    task_id          INTEGER,
    analyzed_at      TEXT,
    release_version  TEXT,
    source_structure TEXT,
    canonical_gap    TEXT,
    peer_comparison  TEXT,
    overall_score    INTEGER CHECK(overall_score BETWEEN 1 AND 10),
    UNIQUE(project_id, task_id)
);

CREATE TABLE IF NOT EXISTS opportunities (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       TEXT,
    task_id          INTEGER,
    source_type      TEXT,
    source_ref       TEXT,
    title            TEXT,
    description      TEXT,
    canonical_status TEXT,
    peer_status      TEXT,
    value            TEXT,
    difficulty       TEXT,
    urgency          TEXT,
    maintainer_signal TEXT,
    impl_hint        TEXT,
    issue_number     INTEGER,
    issue_reactions  INTEGER,
    has_linked_pr    INTEGER,
    value_evidence       TEXT,
    difficulty_evidence  TEXT,
    urgency_evidence     TEXT,
    maintainer_evidence  TEXT,
    status           TEXT DEFAULT 'open',
    first_seen_at    TEXT,
    last_seen_at     TEXT,
    UNIQUE(project_id, source_type, source_ref)
);

CREATE TABLE IF NOT EXISTS discovery_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT,
    source        TEXT,
    raw_signal    TEXT,
    discovered_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_date_status    ON tasks(task_date, status);
CREATE INDEX IF NOT EXISTS idx_tasks_date_type      ON tasks(task_date, task_type);
CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status);
CREATE INDEX IF NOT EXISTS idx_projects_status      ON projects(status);
CREATE INDEX IF NOT EXISTS idx_opps_value           ON opportunities(value);
CREATE INDEX IF NOT EXISTS idx_meta_filter_status   ON project_meta(filter_status);
"""

def _migrate_tasks_unique(conn: sqlite3.Connection):
    """为存量 tasks 表补加 UNIQUE(project_id, task_date, task_type) 约束。
    SQLite 不支持 ALTER TABLE ADD CONSTRAINT，需重建表。"""
    # 检查 tasks 表是否存在（上次迁移可能在 DROP TABLE tasks 后崩溃）
    tasks_exists = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tasks'"
    ).fetchone()[0]
    tasks_new_exists = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tasks_new'"
    ).fetchone()[0]

    if tasks_exists and tasks_new_exists:
        # 上次迁移在 INSERT 后、DROP TABLE tasks 前崩溃（tasks 仍完整，tasks_new 是多余残留）
        # tasks 本身未被修改，直接丢弃 tasks_new 即可；不能 RENAME，因为 tasks 还在
        conn.executescript("DROP TABLE tasks_new;")
        print("DB migration: dropped orphaned tasks_new (tasks table is intact).")
        # 继续往下走，重新检查 tasks 的 UNIQUE 约束是否已存在

    if not tasks_exists and tasks_new_exists:
        # 上次迁移在 DROP TABLE tasks 后、RENAME 前崩溃，直接完成 RENAME
        conn.executescript("""
            ALTER TABLE tasks_new RENAME TO tasks;
            CREATE INDEX IF NOT EXISTS idx_tasks_date_status    ON tasks(task_date, status);
            CREATE INDEX IF NOT EXISTS idx_tasks_date_type      ON tasks(task_date, task_type);
            CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status);
        """)
        print("DB migration: tasks recovered from interrupted migration.")
        return

    if not tasks_exists:
        # tasks 表完全丢失且无 tasks_new，无法恢复，重建空表
        conn.executescript("""
            CREATE TABLE tasks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id      TEXT,
                task_date       TEXT,
                task_type       TEXT,
                trigger_reason  TEXT,
                status          TEXT DEFAULT 'pending',
                created_at      TEXT,
                started_at      TEXT,
                finished_at     TEXT,
                UNIQUE(project_id, task_date, task_type)
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_date_status    ON tasks(task_date, status);
            CREATE INDEX IF NOT EXISTS idx_tasks_date_type      ON tasks(task_date, task_type);
            CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status);
        """)
        print("DB migration: tasks table recreated (data loss).")
        return

    # SQLite implicit UNIQUE indexes have sql=NULL in sqlite_master, so use pragma_index_list instead
    indexes = conn.execute("PRAGMA index_list('tasks')").fetchall()
    for idx in indexes:
        idx_name = idx[1]  # (seq, name, unique, origin, partial)
        if idx[2] == 1:    # unique=1
            cols = [row[2] for row in conn.execute(f"PRAGMA index_info('{idx_name}')").fetchall()]
            if set(cols) == {'project_id', 'task_date', 'task_type'}:
                return
    # 清理可能因上次迁移中途崩溃残留的临时表
    conn.executescript("DROP TABLE IF EXISTS tasks_new;")
    # 检测旧表中是否存在重复 (project_id, task_date, task_type) 行
    # INSERT OR IGNORE 会静默丢弃重复行，迁移前打印 WARN 便于发现数据问题
    total_rows = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    distinct_rows = conn.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT project_id, task_date, task_type FROM tasks)"
    ).fetchone()[0]
    if total_rows != distinct_rows:
        print(f"WARN: DB migration: tasks 表存在 {total_rows - distinct_rows} 条重复 "
              f"(project_id, task_date, task_type) 记录（共 {total_rows} 行，去重后 {distinct_rows} 行）。"
              f"INSERT OR IGNORE 将静默丢弃这些重复行，迁移后任务历史行数会减少。")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks_new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id      TEXT,
            task_date       TEXT,
            task_type       TEXT,
            trigger_reason  TEXT,
            status          TEXT DEFAULT 'pending',
            created_at      TEXT,
            started_at      TEXT,
            finished_at     TEXT,
            UNIQUE(project_id, task_date, task_type)
        );
        INSERT OR IGNORE INTO tasks_new
            SELECT id, project_id, task_date, task_type, trigger_reason,
                   status, created_at, started_at, finished_at
            FROM tasks;
        DROP TABLE tasks;
        ALTER TABLE tasks_new RENAME TO tasks;
        CREATE INDEX IF NOT EXISTS idx_tasks_date_status    ON tasks(task_date, status);
        CREATE INDEX IF NOT EXISTS idx_tasks_date_type      ON tasks(task_date, task_type);
        CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status);
    """)
    print("DB migration: tasks table UNIQUE constraint added.")


def _migrate_tasks_type_check(conn: sqlite3.Connection):
    """为存量 tasks 表的 task_type 列补加 CHECK 约束，限制合法值。
    SQLite 不支持 ALTER TABLE ADD CONSTRAINT，需重建表。
    非法 task_type（如大小写错误 'Triggered'、'bulk-first' 等）在调度/分析逻辑中会静默失效——
    任务永远不被正确匹配，导致项目卡死。CHECK 约束让数据库层拦截非法写入，暴露 LLM 写入错误。
    仅当表上尚无该 CHECK 约束时执行迁移（通过 sqlite_master sql 精确判断）。"""
    # 崩溃恢复：若上次迁移在 DROP TABLE tasks 之后、RENAME 之前崩溃，
    # tasks 不存在但 tasks_type_check_new 存在 → 直接完成 RENAME
    type_check_new_exists = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tasks_type_check_new'"
    ).fetchone()[0]
    tasks_exists = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='tasks'"
    ).fetchone()[0]

    if not tasks_exists and type_check_new_exists:
        conn.executescript("""
            ALTER TABLE tasks_type_check_new RENAME TO tasks;
            CREATE INDEX IF NOT EXISTS idx_tasks_date_status    ON tasks(task_date, status);
            CREATE INDEX IF NOT EXISTS idx_tasks_date_type      ON tasks(task_date, task_type);
            CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status);
        """)
        print("DB migration: tasks recovered from interrupted type_check migration.")
        return

    if tasks_exists and type_check_new_exists:
        # tasks 仍完整，tasks_type_check_new 是多余残留，丢弃后重新检查
        conn.executescript("DROP TABLE tasks_type_check_new;")
        print("DB migration: dropped orphaned tasks_type_check_new (tasks table is intact).")

    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'"
    ).fetchone()
    if row is None:
        return  # 表不存在，_migrate_tasks_unique 会处理
    # 精确检测：要求 DDL 同时包含 CHECK 和 task_type 关键词（排除其他表/约束误判）
    sql_upper = (row[0] or '').upper()
    if 'CHECK' in sql_upper and 'TASK_TYPE' in sql_upper:
        return  # task_type CHECK 约束已存在，幂等退出
    # 存量数据中可能有非法 task_type（如 LLM 历史写入错误），先统计并打印 WARN
    invalid_rows = conn.execute("""
        SELECT COUNT(*) FROM tasks
        WHERE task_type NOT IN ('triggered', 'incremental', 'bulk_first', 'bulk_followup')
    """).fetchone()[0]
    if invalid_rows > 0:
        print(f"WARN: DB migration: tasks 表存在 {invalid_rows} 条非法 task_type 记录，"
              f"将在迁移中被 INSERT OR IGNORE 静默跳过（这些记录不在合法值集合内，说明历史写入有误）。")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks_type_check_new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id      TEXT,
            task_date       TEXT,
            task_type       TEXT CHECK(task_type IN ('triggered', 'incremental', 'bulk_first', 'bulk_followup')),
            trigger_reason  TEXT,
            status          TEXT DEFAULT 'pending',
            created_at      TEXT,
            started_at      TEXT,
            finished_at     TEXT,
            UNIQUE(project_id, task_date, task_type)
        );
        INSERT OR IGNORE INTO tasks_type_check_new
            SELECT id, project_id, task_date, task_type, trigger_reason,
                   status, created_at, started_at, finished_at
            FROM tasks
            WHERE task_type IN ('triggered', 'incremental', 'bulk_first', 'bulk_followup');
        DROP TABLE tasks;
        ALTER TABLE tasks_type_check_new RENAME TO tasks;
        CREATE INDEX IF NOT EXISTS idx_tasks_date_status    ON tasks(task_date, status);
        CREATE INDEX IF NOT EXISTS idx_tasks_date_type      ON tasks(task_date, task_type);
        CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status);
    """)
    print("DB migration: tasks.task_type CHECK constraint added.")


def _migrate_analyses_score_check(conn: sqlite3.Connection):
    """为存量 analyses 表补加 CHECK(overall_score BETWEEN 1 AND 10) 约束。
    SQLite 不支持 ALTER TABLE ADD CONSTRAINT，需重建表。
    仅当表上尚无该 CHECK 约束时执行迁移（通过 sqlite_master sql 判断）。"""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='analyses'"
    ).fetchone()
    if row is None:
        return  # 表不存在，_migrate_analyses_unique 会处理
    if 'CHECK' in (row[0] or '').upper():
        return  # CHECK 约束已存在，幂等退出
    # 重建表：先将越界数据夹到边界（1~10），避免迁移时被 CHECK 拒绝
    # 越界值（0 或 11）说明 LLM 历史上写过非法数据，修正为最近合法边界值
    conn.executescript("""
        UPDATE analyses SET overall_score = 1  WHERE overall_score < 1;
        UPDATE analyses SET overall_score = 10 WHERE overall_score > 10;
    """)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS analyses_check_new (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id       TEXT,
            task_id          INTEGER,
            analyzed_at      TEXT,
            release_version  TEXT,
            source_structure TEXT,
            canonical_gap    TEXT,
            peer_comparison  TEXT,
            overall_score    INTEGER CHECK(overall_score BETWEEN 1 AND 10),
            UNIQUE(project_id, task_id)
        );
        INSERT OR IGNORE INTO analyses_check_new
            SELECT id, project_id, task_id, analyzed_at, release_version,
                   source_structure, canonical_gap, peer_comparison, overall_score
            FROM analyses;
        DROP TABLE analyses;
        ALTER TABLE analyses_check_new RENAME TO analyses;
    """)
    print("DB migration: analyses.overall_score CHECK(1~10) constraint added.")


def _migrate_analyses_unique(conn: sqlite3.Connection):
    """为存量 analyses 表补加 UNIQUE(project_id, task_id) 约束。"""
    # 检查 analyses 表是否存在（防止上次迁移在 DROP TABLE 后崩溃）
    analyses_exists = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='analyses'"
    ).fetchone()[0]
    analyses_new_exists = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='analyses_new'"
    ).fetchone()[0]

    if analyses_exists and analyses_new_exists:
        # 上次迁移在 INSERT 后、DROP TABLE analyses 前崩溃（analyses 仍完整，analyses_new 是多余残留）
        conn.executescript("DROP TABLE analyses_new;")
        print("DB migration: dropped orphaned analyses_new (analyses table is intact).")
        # 继续往下走，重新检查 analyses 的 UNIQUE 约束是否已存在

    if not analyses_exists and analyses_new_exists:
        conn.executescript("ALTER TABLE analyses_new RENAME TO analyses;")
        print("DB migration: analyses recovered from interrupted migration.")
        return

    if not analyses_exists:
        conn.executescript("""
            CREATE TABLE analyses (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id       TEXT,
                task_id          INTEGER,
                analyzed_at      TEXT,
                release_version  TEXT,
                source_structure TEXT,
                canonical_gap    TEXT,
                peer_comparison  TEXT,
                overall_score    INTEGER CHECK(overall_score BETWEEN 1 AND 10),
                UNIQUE(project_id, task_id)
            );
        """)
        print("DB migration: analyses table recreated (data loss).")
        return

    indexes = conn.execute("PRAGMA index_list('analyses')").fetchall()
    for idx in indexes:
        if idx[2] == 1:  # unique=1
            cols = [row[2] for row in conn.execute(f"PRAGMA index_info('{idx[1]}')").fetchall()]
            if set(cols) == {'project_id', 'task_id'}:
                return
    conn.executescript("DROP TABLE IF EXISTS analyses_new;")
    # 检测旧表中是否存在重复 (project_id, task_id) 行
    # INSERT OR IGNORE 会静默丢弃重复行，迁移前打印 WARN 便于发现数据问题
    total_rows = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    distinct_rows = conn.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT project_id, task_id FROM analyses)"
    ).fetchone()[0]
    if total_rows != distinct_rows:
        print(f"WARN: DB migration: analyses 表存在 {total_rows - distinct_rows} 条重复 "
              f"(project_id, task_id) 记录（共 {total_rows} 行，去重后 {distinct_rows} 行）。"
              f"INSERT OR IGNORE 将静默丢弃这些重复行，迁移后分析历史行数会减少。")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS analyses_new (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id       TEXT,
            task_id          INTEGER,
            analyzed_at      TEXT,
            release_version  TEXT,
            source_structure TEXT,
            canonical_gap    TEXT,
            peer_comparison  TEXT,
            overall_score    INTEGER CHECK(overall_score BETWEEN 1 AND 10),
            UNIQUE(project_id, task_id)
        );
        INSERT OR IGNORE INTO analyses_new
            SELECT id, project_id, task_id, analyzed_at, release_version,
                   source_structure, canonical_gap, peer_comparison, overall_score
            FROM analyses;
        DROP TABLE analyses;
        ALTER TABLE analyses_new RENAME TO analyses;
    """)
    print("DB migration: analyses table UNIQUE constraint added.")


def _repair_orphan_project_meta(conn: sqlite3.Connection):
    """修复孤立的 projects 记录：有 projects 行但无对应 project_meta 行。
    原因：discover.py 在 projects INSERT 成功后、project_meta INSERT 前进程被 SIGKILL，
    或磁盘满导致第二条写入失败（两次写入在同一逻辑批次但不在同一 SQLite 语句）。
    这类孤立记录不会出现在 filter.md 的 JOIN 查询中，导致项目永久丢失在过滤队列之外。"""
    result = conn.execute("""
        INSERT OR IGNORE INTO project_meta (project_id, filter_status)
        SELECT p.id, 'pending'
        FROM projects p
        WHERE NOT EXISTS (
            SELECT 1 FROM project_meta m WHERE m.project_id = p.id
        )
          AND p.status NOT IN ('filtered_skip', 'active')
    """)
    if result.rowcount > 0:
        print(f"DB repair: 修复 {result.rowcount} 条孤立 projects 记录（补写 project_meta 行）。")


def _repair_filter_status_mismatch(conn: sqlite3.Connection):
    """修复 filter.md 部分写入导致的状态不一致：
    project_meta.filter_status='keep' 但 projects.status='discovered'。
    原因：filter.md 要求对每个保留项目执行两条 UPDATE（先更新 project_meta，再更新 projects），
    若 LLM 只执行了第一条后进程中断，projects.status 仍为 'discovered'。
    此类项目既不在过滤队列（filter_status != 'pending'）也不在调度队列（status != 'bulk_pending'），
    会永久丢失，schedule.py 永远不会为其生成任务。
    修复方法：将 project_meta.filter_status='keep' 但 projects.status='discovered' 的项目
    的 projects.status 推进到 'bulk_pending'，补全 filter.md 未完成的第二条 UPDATE。"""
    result = conn.execute("""
        UPDATE projects
        SET status = 'bulk_pending'
        WHERE status = 'discovered'
          AND id IN (
              SELECT project_id FROM project_meta WHERE filter_status = 'keep'
          )
    """)
    if result.rowcount > 0:
        print(f"DB repair: 修复 {result.rowcount} 条 filter 状态不一致记录"
              f"（project_meta.filter_status='keep' 但 projects.status='discovered'，已推进至 'bulk_pending'）.")


def _repair_skip_status_mismatch(conn: sqlite3.Connection):
    """修复 filter.md 部分写入的反向情形：
    project_meta.filter_status='skip' 但 projects.status='discovered'。
    与 _repair_filter_status_mismatch 对称，同样是 LLM 只执行第一条 UPDATE 的后果。
    修复方法：将 projects.status 推进到 'filtered_skip'。"""
    result = conn.execute("""
        UPDATE projects
        SET status = 'filtered_skip'
        WHERE status = 'discovered'
          AND id IN (
              SELECT project_id FROM project_meta WHERE filter_status = 'skip'
          )
    """)
    if result.rowcount > 0:
        print(f"DB repair: 修复 {result.rowcount} 条 skip 状态不一致记录"
              f"（project_meta.filter_status='skip' 但 projects.status='discovered'，已推进至 'filtered_skip'）.")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # 启用 WAL 模式：允许并发读写（读不阻塞写，写不阻塞读），减少 "database is locked" 错误。
    # WAL 模式是持久化的（写入 DB 文件头），只需设置一次；幂等，重复设置无副作用。
    conn.execute("PRAGMA journal_mode=WAL")
    # WAL 模式下 synchronous=NORMAL 安全（崩溃不丢数据，仅损失最后一次 checkpoint）且性能更好。
    # busy_timeout=5000：并发访问时最多等待 5 秒再返回 SQLITE_BUSY，而非默认的立即失败（0ms）。
    # analyze.md 以 LLM 进程写入 DB，不受 flock 互斥锁保护，busy_timeout 提供额外的安全裕量。
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate_tasks_unique(conn)
    conn.commit()
    _migrate_tasks_type_check(conn)
    conn.commit()
    _migrate_analyses_unique(conn)
    conn.commit()
    _migrate_analyses_score_check(conn)
    conn.commit()
    _repair_orphan_project_meta(conn)
    conn.commit()
    _repair_filter_status_mismatch(conn)
    conn.commit()
    _repair_skip_status_mismatch(conn)
    conn.commit()
    conn.close()
    print(f"DB initialized: {DB_PATH}")

if __name__ == '__main__':
    init_db()
