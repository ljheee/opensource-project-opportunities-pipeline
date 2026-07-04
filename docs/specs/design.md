# GitHub 开源机会分析 Pipeline 设计文档

> **版本**：v1.0
> **日期**：2026-04-15
> **目标**：自动化发现规模适中、有真实用户群体的开源项目，识别当前语言版本相对原版/其他语言版本的功能差距，输出切实可行的贡献机会。

---

## 一、整体架构

### 1.1 核心分工

| 执行环境 | 负责阶段 | 触发方式 |
|---------|---------|---------|
| GitHub Actions | Stage 1 Discover：多源抓取候选项目 | 每天 UTC 01:00 自动触发 |
| GitHub Actions | Stage 2 Schedule：调度决策，生成今日任务清单 | 同上 |
| 本地 Mac | Stage 3 Filter：Claude Code 语义过滤 | 手动运行 run.sh |
| 本地 Mac | Stage 4 Analyze：Claude Code 深层分析 | 手动运行 run.sh |
| 本地 Mac | Stage 5 Report：生成今日 Markdown 摘要 | run.sh 末尾自动执行 |

### 1.2 目录结构

```
github-opportunities/
└── pipeline/
    ├── .github/workflows/
    │   ├── discover.yml          # 每天定时触发 Stage 1+2
    │   └── manual.yml            # 手动触发（补跑存量用）
    ├── stages/
    │   ├── discover.py           # Stage 1: 多源发现候选项目
    │   ├── schedule.py           # Stage 2: 调度决策，输出今日任务
    │   └── report.py             # Stage 5: 读 SQLite 生成 Markdown
    ├── prompts/
    │   ├── filter.md             # Claude Code Stage 3 指令
    │   └── analyze.md            # Claude Code Stage 4 指令
    ├── data/
    │   ├── pipeline.db           # SQLite 主库
    │   └── reports/              # 每日 Markdown 摘要，按日期命名
    ├── docs/
    │   └── specs/
    │       └── design.md
    ├── run.sh                    # 日常增量入口
    ├── run_bulk.sh               # 首次存量消化入口
    └── requirements.txt
```

### 1.3 完整数据流

```
[GH Actions - 每天 UTC 01:00]
  Stage 1: discover.py    → 多源抓取，写入 projects 表
  Stage 2: schedule.py    → 调度决策，写入 tasks 表
  git commit & push

[本地 Mac - 手动触发]
  git pull
  ./run.sh 或 ./run_bulk.sh
    Stage 3: claude filter.md     → 语义过滤，更新 project_meta
    Stage 4: claude analyze.md    → 深层分析，写入 analyses + opportunities
    Stage 5: python report.py     → 生成 data/reports/YYYY-MM-DD.md
  git push
```

---
## 二、数据模型（SQLite）

### 2.1 projects — 项目基础信息

```sql
CREATE TABLE projects (
    id              TEXT PRIMARY KEY,  -- "{owner}/{repo}"
    name            TEXT,
    url             TEXT,
    language        TEXT,              -- 目标语言（Go/Rust/Python等）
    stars           INTEGER,
    open_issues     INTEGER,
    last_commit_at  TEXT,              -- ISO8601
    latest_release  TEXT,              -- 最新版本号
    latest_release_at TEXT,            -- 发布时间
    topics          TEXT,              -- JSON array
    description     TEXT,
    archived        INTEGER DEFAULT 0, -- 0/1，GitHub 仓库是否已归档
                                       -- 渠道1/3/4 通过 API 直接获取；
                                       -- 渠道2（Trending scraping）需额外调 /repos/{owner}/{repo} 获取
    source          TEXT,              -- 发现来源: github_topic/trending/ecosystem/anchor
    status          TEXT,              -- 见2.7状态机
    first_seen_at   TEXT,
    prev_stars       INTEGER,          -- 上次抓取时的 stars，用于 incremental 变化检测
    prev_open_issues INTEGER,          -- 上次抓取时的 open_issues
    last_fetched_at TEXT
);
```

### 2.2 project_meta — 多语言版本关系

```sql
CREATE TABLE project_meta (
    project_id      TEXT PRIMARY KEY REFERENCES projects(id),
    canonical_name  TEXT,              -- 原版项目名，如 "Apache Sentinel"
    canonical_lang  TEXT,              -- 原版语言，如 "Java"
    canonical_url   TEXT,              -- 原版 GitHub URL
    canonical_stars INTEGER,
    peer_versions   TEXT,              -- JSON: [{lang, url, stars, completeness_hint}]
    filter_status   TEXT,              -- pending/keep/skip
    filter_reason   TEXT,              -- 跳过原因 或 保留理由
    filtered_at     TEXT
);
```

### 2.3 tasks — 调度任务表

```sql
CREATE TABLE tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT,
    task_date       TEXT,              -- YYYY-MM-DD
    task_type       TEXT,              -- bulk_first/bulk_followup/incremental/triggered
    trigger_reason  TEXT,              -- 触发原因，如 "new_release:v2.1.0" / "issues_delta:+15"
    status          TEXT,              -- pending/running/done/skipped
    created_at      TEXT,
    started_at      TEXT,
    finished_at     TEXT
);
```

`task_type` 四种类型：

| 类型 | 含义 |
|------|------|
| `bulk_first` | 存量项目首次深层分析 |
| `bulk_followup` | 存量项目后续批次 |
| `incremental` | 日常增量（有变更才触发）|
| `triggered` | 特殊触发（重大版本发布等）|

### 2.4 analyses — 项目级分析总结

```sql
CREATE TABLE analyses (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       TEXT,
    task_id          INTEGER,
    analyzed_at      TEXT,
    release_version  TEXT,             -- 分析时的版本快照
    source_structure TEXT,             -- JSON: 目标项目源码结构摘要
    canonical_gap    TEXT,             -- 与原版的总体差距描述
    peer_comparison  TEXT,             -- 与其他语言版本的横向对比
    overall_score    INTEGER           -- 1-10，综合贡献价值评分
);
```

### 2.5 opportunities — 贡献机会明细
analyses 是项目级分析，可能分析出多个机会点opportunities。

```sql
CREATE TABLE opportunities (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       TEXT,
    task_id          INTEGER,          -- 直接关联 tasks，与 analyses 平级

    -- 来源
    source_type      TEXT,             -- issue/feature_gap/security/performance/compatibility
    source_ref       TEXT,             -- issue URL，或 "canonical:Java/v1.8.2"，或 "peer:Rust/src/xxx.rs"

    -- 核心描述
    title            TEXT,
    description      TEXT,             -- Claude 生成的详细说明

    -- 对比上下文
    canonical_status TEXT,             -- 原版怎么做的
    peer_status      TEXT,             -- 其他语言版本的状态

    -- 评估
    value            TEXT,             -- high/medium/low
    difficulty       TEXT,             -- high/medium/low
    urgency          TEXT,             -- high/medium/low
    impl_hint        TEXT,             -- 实现建议：涉及哪些文件，大概工作量

    -- issue 专属字段（source_type=issue 时有值）
    issue_number     INTEGER,
    issue_reactions  INTEGER,
    has_linked_pr    INTEGER,          -- 0/1

    -- evidence（JSON，LLM 填原始证据，scoring.py 据此计算评分）
    value_evidence       TEXT,         -- 见 5.5 节
    difficulty_evidence  TEXT,
    urgency_evidence     TEXT,
    maintainer_evidence  TEXT,

    -- 状态追踪
    status           TEXT,             -- open/claimed/merged/obsolete
    first_seen_at    TEXT,
    last_seen_at     TEXT              -- 每次分析更新，消失则标 obsolete
);
```

唯一性约束：`UNIQUE(project_id, source_type, source_ref)`

**`source_type` 五种类型：**

| 类型 | 含义 |
|------|------|
| `issue` | GitHub issue 里用户呼吁的功能 |
| `feature_gap` | 对比原版/其他语言版本发现的功能缺失 |
| `security` | 安全隐患（依赖漏洞、不安全 API 用法等）|
| `performance` | 性能隐患（锁竞争、内存分配、算法复杂度等）|
| `compatibility` | 与原版行为不一致（语义差异、边界条件处理不同）|

### 2.6 discovery_log — 发现来源去重日志

```sql
CREATE TABLE discovery_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT,
    source        TEXT,                -- 哪个渠道发现的
    raw_signal    TEXT,                -- 原始信号，如 HN 帖子标题
    discovered_at TEXT
);
```

多源发现同一项目时，`projects` 只保留一条，`discovery_log`
记录所有来源。**多个渠道都发现同一项目，本身是"有真实用户群体"的强信号。**

### 2.7 项目状态机

```
         发现                  Claude过滤
discovered ──────► filtered_keep ──► bulk_pending
     │                                    │
     │                              首次分析完成
     ▼                                    │
filtered_skip                             ▼
（永久终态）                           active
                                       ↑    │
                                       │    │ 触发条件满足
                                       │    ▼
                                       └─ analyzing
                                         （瞬态）
```

| 状态 | 含义 | 转入 | 转出 |
|------|------|------|------|
| `discovered` | 刚发现，待过滤 | 任意渠道发现 | Claude 过滤后 |
| `filtered_skip` | 永久跳过 | Claude 判断护城河/停维/示例 | 无（终态，人工干预除外）|
| `filtered_keep` | 保留，待排队 | Claude 判断值得分析 | Stage 3 直接写入 `bulk_pending`，不在此状态停留 |
| `bulk_pending` | 存量队列中 | Stage 3 过滤通过后直接写入 | 首次分析完成 |
| `active` | 日常监控中 | 首次分析完成 | 触发条件满足时进入 `analyzing` |
| `analyzing` | 分析进行中 | 触发条件满足 | 分析完成后回到 `active` |

**状态流转职责划分：**

| 谁 | 负责哪些状态变更 |
|----|----------------|
| `discover.py` | → `discovered` |
| `schedule.py` | 写 `tasks` 表，不直接改 `projects` 状态 |
| Claude Code Stage 3 | → `filtered_skip` / `filtered_keep` / `bulk_pending` |
| Claude Code Stage 4 | → `analyzing`（开始时）/ `active`（完成时）|

---

 ## 三、调度策略

### 3.1 调度决策树

`schedule.py` 每天按以下优先级生成今日任务清单，写入 `tasks` 表：

```
Priority 1: triggered 任务（最高优先级）
  条件：project.status = active 且 latest_release_at 有更新（版本号变化）
  → 无论上次分析多近，今天重新分析
  → trigger_reason = "new_release:v2.1.0"

Priority 2: incremental 任务
  条件（同时满足）：
    - project.status = active
    - 距上次分析 >= 7 天
    - 对比 projects 表 prev_* 字段与当前值，以下任一有变化：
        open_issues 数量变化 > 10%（|open_issues - prev_open_issues| / prev_open_issues）
        stars 增长 > 5%（|stars - prev_stars| / prev_stars）
        last_commit_at 有更新
    - 若 prev_stars 为 NULL（新项目首次进入 active），视为有变化，直接触发
  → trigger_reason = "issues_delta:+15" 等

Priority 3: bulk_first 任务（A 类存量消化）
  条件：project.status = bulk_pending 且 source 包含 anchor/ecosystem
  → 按 stars 降序排列
  → 每天最多取 N 个（默认 5，可配置）
  → 分析完成后：bulk_pending → active

Priority 4: bulk_followup 任务（B 类存量消化）
  条件：project.status = bulk_pending 且 非 Priority 3（单源、非 anchor/ecosystem）
       且 当天无 Priority 3 任务（A 类已消化完毕）
  → 按 stars 降序排列
  → 每天最多取 M 个（默认 3，可配置）
  → 分析完成后：bulk_pending → active

Priority 5: 无任务
  → 今日无需分析，输出空清单，GH Actions 正常结束
```

### 3.2 跳过条件

命中以下任一条件，不生成任务：

```
- project.status = filtered_skip
- 距上次分析 < 3 天 且 无新 release 且 无显著变化
- project.archived = true
- open_issues = 0 且 距上次分析 < 30 天
```

### 3.3 每日任务量上限

```python
MAX_TASKS_PER_DAY = {
    "triggered":     None,  # 重大版本必须分析，不限量
    "incremental":   10,    # 日常增量最多 10 个
    "bulk_first":    5,     # 存量每天最多 5 个
    "bulk_followup": 3,     # 后续批次每天最多 3 个
}
# 单次 claude session 建议总任务不超过 15 个
```

### 3.4 存量分批策略（首次投入使用）

```
第一层（bulk_first，A 类）：
  filter_status = keep 且 source 包含 anchor/ecosystem
  → 有明确原版对标，优先分析
  → 每天 5 个，约 2 周内消化完

第二层（bulk_followup，B 类）：
  filter_status = keep 且 非第一层
  → 按 stars 降序
  → 第一层消化完后自动开始

新发现项目插队规则：
  discovery_log 中 >= 2 个不同来源 → 插入第一层队首
  单源发现                         → 追加到对应层队尾
```

### 3.5 task.status 与 project.status 对应关系

```
task.status = pending  → project.status 不变
task.status = running  → project.status = analyzing
task.status = done     → project.status = active
task.status = skipped  → project.status 不变
```

---
 ## 四、多源发现策略

### 4.1 四个发现渠道

**渠道 1：GitHub Topics 搜索**

```python
TOPICS = [
    "microservices", "rate-limiting", "circuit-breaker",
    "job-scheduler", "service-discovery", "message-queue",
    "distributed-tracing", "orm", "cache", "workflow",
    "rpc", "configuration", "load-balancer", "actor-model",
    "distributed-lock", "task-queue", "event-driven"
]
LANGUAGES = ["Go", "Rust", "Python", "TypeScript"]
STAR_RANGE = (300, 15000)
```

每个 topic × 每种语言调一次 GitHub Search API，过滤 archived、fork。

---

**渠道 2：GitHub Trending**

```python
# https://github.com/trending/{language}?since=weekly
TRENDING_LANGUAGES = ["go", "rust", "python", "typescript"]
TRENDING_PERIODS = ["weekly", "monthly"]
```

Trending 项目是"有真实用户群体"的强信号。

---

**渠道 3：知名生态子项目（Ecosystem）**

以已知大型开源组织为锚点，抓取其 GitHub org 下的所有 repo：

```python
ECOSYSTEMS = [
    "apache",           # dubbo-go, rocketmq-client-go, skywalking-go...
    "alibaba",          # sentinel-golang, nacos-sdk-go...
    "cloudwego",        # kitex, hertz...
    "go-kratos",
    "asynkron",         # protoactor-go
    "nats-io",
    "connectrpc",
    "temporal-io",
    "cadence-workflow",
    "uber-go",
]
```

---

**渠道 4：原版锚点反向发现（Anchor）**

以知名原版项目为锚点，搜索各语言的移植版：

```python
ANCHORS = [
    # ── 限流 / 熔断 / 可靠性 ──────────────────────────────────────────
    {"name": "Apache Sentinel",   "lang": "Java",   "keywords": ["sentinel", "rate-limit", "circuit-breaker"]},
    {"name": "Resilience4j",      "lang": "Java",   "keywords": ["resilience4j", "circuit-breaker", "retry"]},
    {"name": "Hystrix",           "lang": "Java",   "keywords": ["hystrix", "circuit-breaker"]},
    {"name": "Failsafe",          "lang": "Java",   "keywords": ["failsafe", "retry", "circuit-breaker"]},
    {"name": "Bucket4j",          "lang": "Java",   "keywords": ["bucket4j", "rate-limit", "token-bucket"]},
    {"name": "Guava RateLimiter", "lang": "Java",   "keywords": ["rate-limiter", "token-bucket", "leaky-bucket"]},

    # ── RPC 框架 ──────────────────────────────────────────────────────
    {"name": "Apache Dubbo",      "lang": "Java",   "keywords": ["dubbo", "rpc"]},
    {"name": "Apache Thrift",     "lang": "C++",    "keywords": ["thrift", "rpc"]},
    {"name": "Tars",              "lang": "C++",    "keywords": ["tars", "tarscpp", "rpc"]},
    {"name": "SOFARPC",           "lang": "Java",   "keywords": ["sofarpc", "rpc"]},
    {"name": "Finagle",           "lang": "Scala",  "keywords": ["finagle", "rpc"]},
    {"name": "Cap'n Proto",       "lang": "C++",    "keywords": ["capnproto", "capnp", "rpc"]},

    # ── Actor 框架 ────────────────────────────────────────────────────
    {"name": "Akka",              "lang": "Scala",  "keywords": ["akka", "actor"]},
    {"name": "Erlang/OTP",        "lang": "Erlang", "keywords": ["erlang", "otp", "actor", "gen-server"]},
    {"name": "Microsoft Orleans", "lang": "C#",     "keywords": ["orleans", "virtual-actor", "grain"]},
    {"name": "Proto.Actor",       "lang": "C#",     "keywords": ["proto-actor", "protoactor"]},

    # ── 任务调度 ──────────────────────────────────────────────────────
    {"name": "Quartz Scheduler",  "lang": "Java",   "keywords": ["quartz", "job-scheduler", "cron"]},
    {"name": "XXL-JOB",           "lang": "Java",   "keywords": ["xxl-job", "distributed-job"]},
    {"name": "Elastic-Job",       "lang": "Java",   "keywords": ["elastic-job", "shardingsphere-elasticjob"]},
    {"name": "Airflow",           "lang": "Python", "keywords": ["airflow", "dag", "workflow-scheduler"]},
    {"name": "Prefect",           "lang": "Python", "keywords": ["prefect", "workflow", "dataflow"]},

    # ── 工作流引擎 ────────────────────────────────────────────────────
    {"name": "Temporal",          "lang": "Go",     "keywords": ["temporal", "workflow", "durable-execution"]},
    {"name": "Cadence",           "lang": "Go",     "keywords": ["cadence", "workflow", "uber"]},
    {"name": "Camunda",           "lang": "Java",   "keywords": ["camunda", "workflow", "bpmn"]},
    {"name": "Activiti",          "lang": "Java",   "keywords": ["activiti", "workflow", "bpmn"]},
    {"name": "Flowable",          "lang": "Java",   "keywords": ["flowable", "workflow", "bpmn"]},

    # ── 规则引擎 ──────────────────────────────────────────────────────
    {"name": "Drools",            "lang": "Java",   "keywords": ["drools", "rule-engine", "kie"]},
    {"name": "Easy Rules",        "lang": "Java",   "keywords": ["easy-rules", "rule-engine"]},

    # ── 缓存 ──────────────────────────────────────────────────────────
    {"name": "Caffeine Cache",    "lang": "Java",   "keywords": ["caffeine", "local-cache"]},
    {"name": "Hazelcast",         "lang": "Java",   "keywords": ["hazelcast", "distributed-cache", "imdg"]},
    {"name": "Ehcache",           "lang": "Java",   "keywords": ["ehcache", "cache"]},
    {"name": "JetCache",          "lang": "Java",   "keywords": ["jetcache", "multilevel-cache"]},
    {"name": "Spring Cache",      "lang": "Java",   "keywords": ["spring-cache", "cache-abstraction"]},

    # ── ORM / 数据访问 ────────────────────────────────────────────────
    {"name": "MyBatis",           "lang": "Java",   "keywords": ["mybatis", "orm", "sql-mapper"]},
    {"name": "Hibernate",         "lang": "Java",   "keywords": ["hibernate", "orm", "jpa"]},
    {"name": "jOOQ",              "lang": "Java",   "keywords": ["jooq", "sql-builder", "type-safe-sql"]},
    {"name": "JDBI",              "lang": "Java",   "keywords": ["jdbi", "sql", "fluent"]},
    {"name": "SQLAlchemy",        "lang": "Python", "keywords": ["sqlalchemy", "orm"]},

    # ── 消息队列 / 流处理 ─────────────────────────────────────────────
    {"name": "Apache RocketMQ",   "lang": "Java",   "keywords": ["rocketmq", "message-queue"]},
    {"name": "Apache Pulsar",     "lang": "Java",   "keywords": ["pulsar", "message-queue", "streaming"]},
    {"name": "Kafka Streams",     "lang": "Java",   "keywords": ["kafka-streams", "stream-processing"]},
    {"name": "Celery",            "lang": "Python", "keywords": ["celery", "task-queue", "distributed-task"]},
    {"name": "Flink",             "lang": "Java",   "keywords": ["flink", "stream-processing", "datastream"]},

    # ── 配置中心 / 注册中心 ───────────────────────────────────────────
    {"name": "Apollo Config",     "lang": "Java",   "keywords": ["apollo", "config-center", "apolloconfig"]},
    {"name": "Nacos",             "lang": "Java",   "keywords": ["nacos", "service-discovery", "config"]},
    {"name": "Spring Cloud Config","lang": "Java",  "keywords": ["spring-config", "config-server"]},
    {"name": "Consul",            "lang": "Go",     "keywords": ["consul", "service-discovery", "kv-store"]},

    # ── 微服务框架 ────────────────────────────────────────────────────
    {"name": "Spring Cloud",      "lang": "Java",   "keywords": ["spring-cloud", "microservices"]},
    {"name": "Micronaut",         "lang": "Java",   "keywords": ["micronaut", "microservices"]},
    {"name": "Quarkus",           "lang": "Java",   "keywords": ["quarkus", "microservices"]},
    {"name": "Vert.x",            "lang": "Java",   "keywords": ["vertx", "reactive", "microservices"]},
    {"name": "ServiceComb",       "lang": "Java",   "keywords": ["servicecomb", "java-chassis", "microservices"]},

    # ── 链路追踪 / 可观测性 ───────────────────────────────────────────
    {"name": "Apache SkyWalking", "lang": "Java",   "keywords": ["skywalking", "apm", "tracing"]},
    {"name": "Zipkin",            "lang": "Java",   "keywords": ["zipkin", "distributed-tracing"]},
    {"name": "Pinpoint",          "lang": "Java",   "keywords": ["pinpoint", "apm", "tracing"]},

    # ── 分布式事务 ────────────────────────────────────────────────────
    {"name": "Seata",             "lang": "Java",   "keywords": ["seata", "distributed-transaction", "saga"]},
    {"name": "Atomikos",          "lang": "Java",   "keywords": ["atomikos", "distributed-transaction", "xa"]},

    # ── 数据同步 / binlog ─────────────────────────────────────────────
    {"name": "Alibaba Canal",     "lang": "Java",   "keywords": ["canal", "binlog", "cdc", "mysql-replication"]},
    {"name": "Debezium",          "lang": "Java",   "keywords": ["debezium", "cdc", "change-data-capture"]},
]
# 搜索策略：GitHub Search "{keyword} in:name,description language:{target_lang}"
```

### 4.2 去重与多源验证

```python
# 去重键："{owner}/{repo}"
# 发现时：
#   - projects 表 upsert（只更新 last_fetched_at）
#   - discovery_log 每次都插入一条新记录

# 多源验证信号：
# SELECT COUNT(DISTINCT source) FROM discovery_log WHERE project_id = ?
# >= 2 个不同渠道发现 → 强信号，插入存量队列队首
# 1  个渠道发现       → 普通信号，追加队尾
```

### 4.3 Python 层规则预过滤

发现后先做廉价规则过滤，减少 Claude 的工作量：

```python
RULE_FILTERS = [
    lambda p: p.stars < 300,                     # star 太少（渠道2/3/4 兜底，渠道1已在搜索层过滤）
    lambda p: p.stars > 15000,                   # 护城河太深（同上）
    lambda p: p.archived == True,                # 已归档
    lambda p: p.last_commit_at < 180_days_ago,   # 超过 6 个月无提交
    lambda p: p.open_issues == 0,                # 无 issue 活动
    lambda p: p.is_fork == True,                 # fork 项目
]
# 命中任一规则 → filter_status = skip，写明原因，不进入 Claude 过滤队列
```

### 4.4 GitHub API 限流处理

```
未认证：       60 req/hour
认证（PAT）：  5000 req/hour  ← GH Actions 用 GITHUB_TOKEN，自动注入
Search API：   30 req/minute  ← 每次搜索间隔 2s
```

超出限流（429）时：记录 `discovery_log.raw_signal = "rate_limited"`，下次自动补跑，不阻断整体流程。

 ---
## 五、Claude Code 分析策略

### 5.1 Stage 3：语义过滤（prompts/filter.md）

**输入**：`project_meta.filter_status = pending` 的项目列表（从 SQLite 读取）

**判断维度**（按顺序，命中即跳过）：

```
1. 护城河判断
   - 该项目本身就是原版（Kafka、Redis、MySQL 本体）
   - 已是所在领域事实标准，当前语言版本即原版（zerolog、resty）
   - 生态依赖极深（coredns、etcd）

2. 项目性质判断
   - 纯 CLI 工具（无库/服务组件属性）
   - 纯示例/教程/脚手架
   - 纯资源列表/awesome 系列
   - 商业产品的开源 SDK/Agent

3. 场景判断
   - 游戏专用框架
   - 区块链/Web3 专用
   - K8s 基础设施层（非应用层组件）
   - IoT 专用平台

4. 通过 → filter_status = keep
   补充 canonical 信息：canonical_name / canonical_lang / canonical_url / peer_versions
   - 能确定原版时尽量填写，用于 feature_gap / compatibility 类机会点的跨语言对照。
   - 无法确定原版 URL，但项目明显属于某类替代实现（如 SQL builder、actor 框架、cron 库等）时，仍可 keep，canonical_* 字段可留空。此时 Stage 4 主要产出 issue / security / performance 类机会点。
```

**输出**：更新 `project_meta` 表的 `filter_status`、`filter_reason`、`filtered_at`；
对 `keep` 项目尽量填写 `canonical_name`、`canonical_lang`、`canonical_url`、`canonical_stars`、`peer_versions`；
将 `keep` 项目的 `projects.status` 更新为 `bulk_pending`。

**canonical_url 的必要性说明**：
- `feature_gap` 和 `compatibility` 类机会点依赖 `canonical_url` 抓取原版实现作为对照证据。
- `issue`、`security`、`performance` 类机会点主要基于目标项目自身信息判断，不强制要求 `canonical_url`。

---

### 5.2 Stage 4：深层分析（prompts/analyze.md）

**输入**：今日 `tasks` 表中 `status = pending` 的任务列表

**每个项目的分析流程**：

```
Step 1: 更新状态
  task.status     = running
  project.status  = analyzing

Step 2: 抓取目标项目信息
  - WebFetch README
  - WebFetch CHANGELOG / releases 页
  - GitHub API：拉取 top 20 open issues（按 reactions 降序）
  - GitHub API：拉取项目目录结构（tree）

Step 3: 抓取原版信息
  - WebFetch canonical_url 的 README / 功能列表
  - 提取原版功能全集（feature matrix）

Step 4: 横向对比其他语言版本
  - 遍历 peer_versions，WebFetch 各版本 README
  - 对比各语言版本功能完整度
  - 判断：目标版本 vs 原版 vs 其他语言版本，谁更领先/落后

Step 5: 源码结构分析
  - WebFetch GitHub 代码树（/tree/main）
  - 识别核心模块，对应原版哪些功能
  - 发现原版有但目标版本完全缺失的模块

Step 6: Issues 深度分析
  - 逐条读取 top issues 正文 + 评论
  - 跳过：已有关联 PR 的 issue
  - 分类：feature_request / bug / performance / security
  - 对比：该功能原版是否已实现？其他语言版本是否已实现？

Step 6.5: 收集 maintainer_evidence
  - GitHub API: GET /repos/<project_id>/pulls?state=closed&per_page=50
    搜索标题/描述含相关关键词的历史 PR，记录：
      number / title / merged(bool) / url / age_days / maintainer_comment（原文）
  - 对已有 issue 的 opportunity，拉取 issue 评论，筛选 author_association
    为 OWNER/COLLABORATOR/MEMBER 的回复，记录原文 body_quote
  - 记录 issue 当前 labels（welcome_labels）
  - 将以上原始数据填入 maintainer_evidence JSON，不做评分判断
  - maintainer_signal / value 修正由 scoring.py 计算

Step 7: 综合输出
  - 写入 analyses 表（项目级总结）
  - 写入 opportunities 表（每个机会点）
    - LLM 填写：source_type/source_ref/title/description/canonical_status/peer_status
                impl_hint/issue_number/issue_reactions/has_linked_pr
                *_evidence 四个 JSON 字段
    - 不填写：value/difficulty/urgency/maintainer_signal（由 scoring.py 计算）
  - task.status    = done
  - project.status = active
```

---

### 5.3 机会点评分标准（规则化）

**评分由 `scoring.py` 根据 evidence 字段计算，LLM 不直接输出评分结论。**

**value 规则**（基于 value_evidence）：

| 条件 | 结果 |
|------|------|
| `canonical_impl_url` 有值 AND `peer_impl_urls` 非空 AND `issue_reactions` >= 5 | `high` |
| `canonical_impl_url` 有值 AND（peer 为空 OR reactions < 5） | `medium` |
| `canonical_impl_url` 无值 | `low` |

**difficulty 规则**（基于 difficulty_evidence）：

| 条件 | 结果 |
|------|------|
| `canonical_impl_url` 无值 | `high` |
| 有值 AND `canonical_impl_loc` > 500 | `high` |
| 有值 AND loc 200–500 | `medium` |
| 有值 AND loc < 200 | `low` |
| `why_hard` 含关键词（核心数据结构/并发设计/语言特性限制） | 上调一级 |

**urgency 规则**（基于 urgency_evidence）：

| 条件 | 结果 |
|------|------|
| `cve_id` 非空 | `high` |
| `has_prod_signal=true` AND `has_workaround=false` | `high` |
| `has_prod_signal=true` AND `has_workaround=true` | `medium` |
| `has_prod_signal=false` AND `has_workaround=false` | `medium` |
| `has_prod_signal=false` AND `has_workaround=true` | `low` |

**maintainer_signal 规则**（基于 maintainer_evidence）：

| 条件 | 结果 |
|------|------|
| `similar_prs` 有 merged=true AND age_days < 365 | `welcoming` |
| `similar_prs` 有 merged=false AND maintainer_comment 含拒绝语义 | `rejected` |
| `welcome_labels` 非空 OR `maintainer_responses` 含正向表态 | `welcoming` |
| welcoming + rejected 同时存在 | 取 age_days 最小的结论 |
| 以上都无 | `unknown` |

**maintainer_signal 对 value 的修正**：

| signal | 修正规则 |
|--------|----------|
| `welcoming` | value 上调一级（low→medium，medium→high） |
| `rejected` | `status = 'obsolete'`，不出现在报告里 |
| `neutral` / `unknown` | 不修正 |

---

### 5.5 各 source_type 的 evidence 结构

**LLM 职责边界**：找到 URL、行号、引用原文 → 填客观字段；解释"为什么" → 填主观字段，且必须基于客观字段推导，不能凭空断言。

#### issue 类

```json
{
  "canonical_impl_url":  "https://github.com/.../HotParamSlot.java",
  "canonical_impl_loc":  320,
  "peer_impl_urls":      ["https://github.com/sentinel-rust/.../hotparam.rs"],
  "issue_reactions":     12,
  "issue_count":         3,
  "has_workaround":      true,
  "prod_signal_quote":   "We hit this in production with 10k rps — issue #234",
  "has_prod_signal":     true,
  "gap_desc":            "sentinel-golang 只有全局 QPS，无 per-key 计数"
}
```

#### feature_gap 类

```json
{
  "canonical_impl_url":   "https://github.com/.../HotParamSlot.java",
  "canonical_impl_loc":   320,
  "peer_impls": [
    {
      "lang": "Rust", "url": "https://...", "loc": 180,
      "completeness": "full",
      "completeness_reason": "实现了 per-key 计数但不支持并发度模式"
    }
  ],
  "target_has_stub":      false,
  "target_related_files": ["pkg/core/stat/"],
  "feature_desc":         "热点参数限流：按请求参数值独立计数",
  "gap_desc":             "sentinel-golang 只有全局 QPS，无 per-key 计数"
}
```

#### security 类

```json
{
  "cve_id":              "CVE-2024-1234",
  "vulnerable_dep":      "golang.org/x/crypto v0.0.1",
  "fixed_in_dep":        "v0.3.0",
  "canonical_fixed":     true,
  "peer_fixed":          [{"lang": "Rust", "fixed": true}],
  "affected_file":       "pkg/transport/tls.go:42",
  "affected_api":        "tls.Config{InsecureSkipVerify: true}",
  "attack_surface":      "中间人攻击，影响所有 TLS 通信场景"
}
```

#### performance 类

```json
{
  "canonical_impl_url":   "https://github.com/.../LongAdder.java",
  "canonical_impl_loc":   95,
  "target_approach_file": "pkg/core/stat/counter.go:15",
  "issue_prod_quotes":    ["40% CPU spike under 5k rps — issue #234"],
  "has_prod_signal":      true,
  "has_workaround":       false,
  "perf_problem_desc":    "当前用 sync.Mutex 全局锁，高并发下锁竞争严重",
  "suggested_approach":   "参考 LongAdder 实现分片计数，或改用 atomic.AddInt64"
}
```

#### compatibility 类

```json
{
  "canonical_behavior_url":  "https://github.com/.../FlowRule.java#L89",
  "target_behavior_file":    "pkg/core/flow/rule.go:56",
  "test_case_exists":        false,
  "issue_refs":              ["#45", "#67"],
  "has_workaround":          false,
  "canonical_behavior_desc": "Java 版滑动窗口，精度 500ms",
  "target_behavior_desc":    "Go 版固定窗口，边界有突刺",
  "impact_desc":             "边界时刻实际放行量可达限额 2 倍"
}
```

#### maintainer_evidence（所有 source_type 共用）

```json
{
  "similar_prs": [
    {
      "number": 42,
      "title":  "feat: add hotspot parameter flow control",
      "merged": false,
      "url":    "https://github.com/.../pulls/42",
      "age_days": 180,
      "maintainer_comment": "out of scope for now"
    }
  ],
  "welcome_labels":       ["help wanted", "good first issue"],
  "maintainer_responses": [
    {"author_association": "OWNER", "body_quote": "PR welcome", "issue_number": 88}
  ]
}
```

### 5.6 scoring.py — 规则引擎

独立于 LLM，在 Stage 4 完成后运行，读取 evidence JSON 按规则计算评分写回数据库。

```
输入：opportunities 表中 value IS NULL 的记录（LLM 刚写入 evidence 但未评分）
输出：更新 value / difficulty / urgency / maintainer_signal / status 字段
```

**职责划分**：
- LLM（analyze.md）：负责信息提取，填 evidence，不打分
- scoring.py：负责评分，规则透明可调，不依赖 LLM

**规则可配置化**：评分阈值（如 `issue_reactions >= 5`、`canonical_impl_loc > 500`）抽取为常量，便于后续调整。

---

### 5.4 Claude Code Session 边界设计

```bash
# Stage 3：过滤（批量处理新发现项目，通常较快）
claude --dangerously-skip-permissions --print \
  "$(cat prompts/filter.md)"

# Stage 4：分析（按任务清单逐个深入，耗时较长）
claude --dangerously-skip-permissions --print \
  "$(cat prompts/analyze.md)"
```

`prompts/filter.md` 和 `prompts/analyze.md` 均为完整自包含指令，包含：
- SQLite 文件绝对路径
- 当前日期
- 明确的输入/输出约定（读哪张表、写哪张表、字段映射）
- 异常处理指令（API 超时、项目 404 等跳过并记录，不阻断整体流程）

---
## 六、运行编排

### 6.1 GH Actions Workflow（discover.yml）

```yaml
name: Daily Discover & Schedule

on:
  schedule:
    - cron: '0 1 * * *'   # 每天 UTC 01:00 = 北京时间 09:00
  workflow_dispatch:        # 支持手动触发（补跑存量用）
    inputs:
      mode:
        description: 'bulk_first / incremental'
        default: 'incremental'

jobs:
  discover:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - run: pip install -r pipeline/requirements.txt

      - name: Stage 1 - Discover
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: python pipeline/stages/discover.py

      - name: Stage 2 - Schedule
        run: |
          python pipeline/stages/schedule.py \
            --mode ${{ github.event.inputs.mode || 'incremental' }}

      - name: Commit results
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add pipeline/data/pipeline.db
          git diff --staged --quiet || \
            git commit -m "chore: daily discover $(date +%Y-%m-%d)"
          git push
```

---

### 6.2 日常增量入口（run.sh）

```bash
#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$PIPELINE_DIR/data/pipeline.db"
PROMPTS="$PIPELINE_DIR/prompts"
STAGES="$PIPELINE_DIR/stages"
DATE=$(date +%Y-%m-%d)

echo "=== GitHub Opportunities Pipeline - $DATE ==="

# 0. 拉取最新状态（GH Actions 已写入今日任务）
echo "[0/4] git pull..."
git -C "$PIPELINE_DIR/.." pull --rebase

# 1. Stage 3: 语义过滤（处理新发现的项目）
# 注意：过滤完成后可能产生新的 bulk_pending 项目，需重新调度
FILTER_COUNT=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM project_meta WHERE filter_status='pending';")

if [ "$FILTER_COUNT" -gt 0 ]; then
  echo "[1/4] Stage 3: 语义过滤 ($FILTER_COUNT 个待过滤项目)..."
  claude --dangerously-skip-permissions --print \
    "$(cat "$PROMPTS/filter.md")"
  # 过滤后重新调度，将新增 bulk_pending 项目纳入今日任务
  echo "[1/4] 重新调度..."
  python "$STAGES/schedule.py" --mode incremental
else
  echo "[1/4] Stage 3: 无待过滤项目，跳过。"
fi

# 检查今日是否有待分析任务（过滤+调度完成后再检查）
PENDING=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status='pending';")

if [ "$PENDING" -eq 0 ]; then
  echo "今日无待分析任务，退出。"
  exit 0
fi

echo "今日待分析任务：$PENDING 个"

# 2. Stage 4: 深层分析
echo "[2/4] Stage 4: 深层分析 ($PENDING 个任务)..."
claude --dangerously-skip-permissions --print \
  "$(cat "$PROMPTS/analyze.md")"

# 3. Stage 5: 生成今日报告
echo "[3/4] Stage 5: 生成报告..."
python "$STAGES/report.py" --date "$DATE"

# 4. 推回 repo
echo "[4/4] git push..."
git -C "$PIPELINE_DIR/.." add \
  pipeline/data/pipeline.db \
  "pipeline/data/reports/$DATE.md"

git -C "$PIPELINE_DIR/.." diff --staged --quiet || \
  git -C "$PIPELINE_DIR/.." commit \
    -m "feat: analysis report $DATE ($PENDING tasks)"

git -C "$PIPELINE_DIR/.." push

echo "=== 完成 ==="
echo "报告：pipeline/data/reports/$DATE.md"
```

---

### 6.3 首次存量消化入口（run_bulk.sh）

```bash
#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$PIPELINE_DIR/data/pipeline.db"
PROMPTS="$PIPELINE_DIR/prompts"
STAGES="$PIPELINE_DIR/stages"
BATCH_SIZE=${1:-5}           # 默认每次跑 5 个，支持参数覆盖
DATE=$(date +%Y-%m-%d)

echo "=== Bulk Analysis - $DATE (batch_size=$BATCH_SIZE) ==="

# 0. 拉取最新
git -C "$PIPELINE_DIR/.." pull --rebase

# 检查存量队列
TOTAL=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM projects WHERE status='bulk_pending';")
DONE=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM projects WHERE status='active';")

echo "存量进度：已完成 $DONE 个 / 待分析 $TOTAL 个"

if [ "$TOTAL" -eq 0 ]; then
  echo "存量队列已清空，请改用 run.sh 进行日常增量。"
  exit 0
fi

# 1. Stage 3: 语义过滤（优先把 pending 项目过滤完）
FILTER_COUNT=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM project_meta WHERE filter_status='pending';")

if [ "$FILTER_COUNT" -gt 0 ]; then
  echo "[1/3] Stage 3: 语义过滤 ($FILTER_COUNT 个待过滤项目)..."
  claude --dangerously-skip-permissions --print \
    "$(cat "$PROMPTS/filter.md")"
fi

# 2. Stage 4: 本批次存量分析
# schedule.py 生成本批次任务（只取 bulk_first/bulk_followup，限量 BATCH_SIZE）
python "$STAGES/schedule.py" --mode bulk_first --batch-size "$BATCH_SIZE"

PENDING=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status='pending';")

echo "[2/3] Stage 4: 深层分析 ($PENDING 个任务)..."
claude --dangerously-skip-permissions --print \
  "$(cat "$PROMPTS/analyze.md")"

# 3. 生成报告 + 推回
echo "[3/3] 生成报告并推送..."
python "$STAGES/report.py" --date "$DATE"

git -C "$PIPELINE_DIR/.." add \
  pipeline/data/pipeline.db \
  "pipeline/data/reports/$DATE.md"

git -C "$PIPELINE_DIR/.." diff --staged --quiet || \
  git -C "$PIPELINE_DIR/.." commit \
    -m "feat: bulk analysis $DATE ($PENDING tasks, $TOTAL remaining)"

git -C "$PIPELINE_DIR/.." push

# 输出剩余进度
REMAINING=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM projects WHERE status='bulk_pending';")
echo "=== 完成 ==="
echo "本批次分析：$PENDING 个 | 剩余存量：$REMAINING 个"
```

---

### 6.4 异常处理

| 异常场景 | 处理方式 |
|---------|---------|
| GH Actions 失败 | 不影响本地，下次 `schedule.py` 补齐任务 |
| Claude Code 中途退出 | `task.status` 停在 `running`，下次 `run.sh` 自动重跑 `running` 状态的任务 |
| GitHub API 限流（429）| `discover.py` 捕获，写入 `discovery_log.raw_signal="rate_limited"`，下次补跑 |
| 项目 404 / 不可访问 | 记录 `filter_reason="fetch_failed"`，不阻断整体流程 |

---

### 6.5 首次使用步骤

```
步骤 1：在 GitHub repo 设置 GITHUB_TOKEN（Actions 自动注入，无需额外配置）
步骤 2：手动触发 GH Actions workflow_dispatch，mode=bulk_first
        → discover.py 全量抓取，schedule.py 生成存量队列
步骤 3：本地连续运行 run_bulk.sh，每天消化一批
        ./pipeline/run_bulk.sh 5    # 每次 5 个
步骤 4：存量消化完毕后，改用日常 run.sh
        ./pipeline/run.sh           # 每天增量
```

