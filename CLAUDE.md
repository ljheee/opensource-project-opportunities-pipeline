# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个自动发现和分析 GitHub 开源项目贡献机会的流水线。核心思路是：找出知名 Java/Python 框架在 Go/Rust/TypeScript 等生态中的移植版或替代实现，通过 LLM 深度分析找出功能缺口，并生成每日机会报告。

## 常用命令

### 环境准备

```bash
cp .env.example .env
# 编辑 .env：设置 GITHUB_TOKEN（强烈建议），必要时调整 CLI_TOOL
pip install -r requirements.txt
```

`.env` 关键变量：
- `GITHUB_TOKEN`：GitHub PAT，未设置时 GitHub API 限额仅 60 req/hour，analyze 阶段容易因限流失败。
- `CLI_TOOL`：调用 LLM 的命令，默认 `claude --dangerously-skip-permissions`，也支持 `cursor-agent -p --force`。

### 日常增量运行

```bash
bash run.sh
```

`run.sh` 会依次执行：git pull → init_db → Stage 3 语义过滤 → Stage 2 调度 → Stage 4 深度分析 → Stage 4.5 评分 → Stage 5 生成报告 → git commit/push。

### 存量消化（首次运行或积压较多时）

```bash
bash run_bulk.sh 10
```

参数为每批分析的项目数，范围 1~100，建议 10~20。重复运行直到提示“存量队列已清空”。

### 单独运行某个阶段

```bash
python stages/init_db.py
python stages/discover.py --dry-run
python stages/schedule.py --mode incremental --dry-run
python stages/schedule.py --mode bulk_first --batch-size 5
python stages/scoring.py
python stages/report.py --date 2026-06-29
```

### 查看数据库状态

```bash
sqlite3 data/pipeline.db "SELECT status, COUNT(*) FROM projects GROUP BY status;"
sqlite3 data/pipeline.db "SELECT filter_status, COUNT(*) FROM project_meta GROUP BY filter_status;"
sqlite3 data/pipeline.db "SELECT task_type, status, COUNT(*) FROM tasks GROUP BY task_type, status;"
```

### 查看报告

```bash
ls data/reports/
cat data/reports/2026-06-29.md
```

## 架构说明

### 流水线阶段

| 阶段 | 脚本 | 运行环境 | 职责 |
|------|------|----------|------|
| Stage 1 Discover | `stages/discover.py` | GitHub Actions | 通过 topics、trending、ecosystems、anchors 多源发现候选项目，写入 `projects` 和 `discovery_log` |
| Stage 2 Schedule | `stages/schedule.py` | GitHub Actions | 根据项目状态变化（新 release、stars/issues/commit 变化）生成当日 `tasks` |
| Stage 3 Filter | `prompts/filter.md` + LLM | 本地 | 语义过滤：判断项目是否为知名框架的移植版/替代实现，并填写 canonical 元数据 |
| Stage 4 Analyze | `prompts/analyze.md` + LLM | 本地 | 深度分析：抓取目标项目、原版项目、peer 版本的 README/结构/issues，识别贡献机会 |
| Stage 4.5 Score | `stages/scoring.py` | 本地 | 读取 `opportunities` 中的 evidence JSON，按规则计算 value/difficulty/urgency/maintainer_signal |
| Stage 5 Report | `stages/report.py` | 本地 | 读取 SQLite 生成 `data/reports/YYYY-MM-DD.md` |

`run.sh` 和 `run_bulk.sh` 是本地入口脚本；GitHub Actions 仅运行 Stage 1 和 Stage 2，由 `.github/workflows/discover.yml` 定义，每天 UTC 17:00 触发。

### 核心数据模型

数据库为 `data/pipeline.db`（SQLite，已纳入 git 追踪，启用 WAL 模式）。

- `projects`：项目基础信息（id、url、language、stars、open_issues、status、source 等）。
- `project_meta`：多语言关系元数据（canonical_name/canonical_lang/canonical_url、filter_status、peer_versions 等）。
- `tasks`：每日调度任务（task_date、task_type、trigger_reason、status）。
- `analyses`：项目级分析摘要（source_structure、canonical_gap、peer_comparison、overall_score）。
- `opportunities`：具体贡献机会（source_type/source_ref、title、value、difficulty、urgency、maintainer_signal、evidence JSON）。
- `discovery_log`：发现来源追踪，用于去重。

项目状态流转：

```
discovered → filtered_keep → bulk_pending → analyzing → active
     |            |
     ▼            ▼
filtered_skip (terminal)
```

### 关键设计决策

- **LLM 通过 prompt 直接操作 SQLite**：`prompts/filter.md` 和 `prompts/analyze.md` 被 `run.sh`/`run_bulk.sh` 渲染后喂给 `CLI_TOOL`；LLM 自行读取/写入 DB。
- **证据与评分分离**：LLM 只产出结构化证据，规则化评分由 `stages/scoring.py` 完成，避免 LLM 直接打分的不稳定性。
- **并发控制**：`run.sh` 与 `run_bulk.sh` 共享 `data/.pipeline.lock`，Linux 用 `flock` 非阻塞锁，macOS 因无 flock 命令仅打印警告，需手动避免并发。
- **运行前自动丢弃本地未提交修改**：两个脚本都会 `git checkout -- .` 再 `git pull --rebase`，本地改动会丢失。
- **`scripts/` 目录是临时产物**：LLM 运行时可能生成临时脚本，已加入 `.gitignore`，不需要版本追踪。
- **无单元测试**：项目没有正式测试，验证靠各 stage 的 `--dry-run`、SQLite 查询以及报告内容检查。
