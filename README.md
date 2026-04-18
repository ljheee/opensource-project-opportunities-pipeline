# Opensource Project Opportunities Pipeline

自动发现并分析 GitHub 上有贡献机会的开源项目——找出知名 Java/Python 框架在 Go/Rust/TypeScript 生态中的移植版或替代实现，评估其完成度缺口。

## 架构概览

```
GitHub API
    │
    ▼
Stage 1: Discover   → projects 表（status=discovered）
    │
    ▼
Stage 3: Filter     → LLM 语义过滤（keep/skip）
    │
    ▼
Stage 4: Analyze    → LLM 深度分析（overall_score 1~10）
    │
    ▼
Stage 5: Report     → data/reports/YYYY-MM-DD.md
```

## 快速开始

### 1. 配置环境

```bash
cp .env.example .env
# 编辑 .env，填入 GITHUB_TOKEN（可选但强烈建议）
```

`.env` 支持的配置项：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CLI_TOOL` | `claude --dangerously-skip-permissions` | LLM CLI 命令 |
| `GITHUB_TOKEN` | 无 | GitHub PAT，未设置时 API 限额仅 60 req/hour |

GITHUB_TOKEN 从 [github.com/settings/tokens](https://github.com/settings/tokens) 生成，需要 `public_repo` read 权限。

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 运行流程

#### 首次运行（存量消化）

GitHub Actions 每天凌晨 1 点自动运行 `discover.yml` 发现新项目。首次 discover 后会积累大量待分析项目，需要在本地用 `run_bulk.sh` 消化：

```bash
bash run_bulk.sh 10
```

参数说明：`10` 是每次运行分析的项目数（batch_size，范围 1~100）。

- 数字越大，单次运行时间越长
- 建议 **10~20**，太大时 LLM 上下文压力大容易出错
- 每次运行完自动 git push，下次从断点继续
- 重复运行直到提示"存量队列已清空"

#### 日常运行（增量模式）

存量消化完后，每天手动或定时跑一次：

```bash
bash run.sh
```

处理当天新发现的项目，生成日报并推送。

## 查看分析结果

### 查看已完成深度分析的项目

```bash
sqlite3 data/pipeline.db "
SELECT p.id, p.language, p.stars, a.overall_score, a.canonical_gap
FROM projects p
JOIN analyses a ON a.project_id = p.id
WHERE p.status = 'analyzed'
ORDER BY a.overall_score DESC;
"
```

### 查看各阶段数量统计

```bash
sqlite3 data/pipeline.db "
SELECT status, COUNT(*) FROM projects GROUP BY status;
"
```

| status | 含义 |
|--------|------|
| `discovered` | 已发现，待语义过滤 |
| `bulk_pending` | 过滤通过，待深度分析 |
| `filtered_skip` | 语义过滤淘汰 |
| `analyzed` | 深度分析完成 |

### 查看过滤结果

```bash
sqlite3 data/pipeline.db "
SELECT filter_status, COUNT(*) FROM project_meta GROUP BY filter_status;
"
```

### 查看生成的报告

```bash
ls data/reports/
cat data/reports/YYYY-MM-DD.md
```

## 目录结构

```
.
├── run.sh              # 日常增量运行脚本
├── run_bulk.sh         # 存量消化运行脚本
├── stages/             # 各阶段 Python 脚本
│   ├── init_db.py      # 初始化/迁移数据库
│   ├── discover.py     # Stage 1: 发现项目
│   ├── schedule.py     # Stage 2: 调度任务
│   ├── scoring.py      # Stage 4.5: 规则评分
│   └── report.py       # Stage 5: 生成报告
├── prompts/            # LLM prompt 模板
│   ├── filter.md       # Stage 3: 语义过滤 prompt
│   └── analyze.md      # Stage 4: 深度分析 prompt
├── data/
│   ├── pipeline.db     # SQLite 数据库（git 追踪）
│   └── reports/        # 生成的日报
├── .env.example        # 环境变量模板
└── .github/workflows/
    └── discover.yml    # 每日自动发现 Action
```

## 注意事项

- **不要并发运行** `run.sh` 和 `run_bulk.sh`，两者共享同一个 SQLite DB
- `scripts/` 目录是 LLM 运行时生成的临时脚本，已加入 `.gitignore`，无需关注
- 每次运行前会自动 `git pull`，**本地未提交的修改会被丢弃**
- macOS 不支持 `flock`，互斥锁会跳过，手动确保不并发运行
