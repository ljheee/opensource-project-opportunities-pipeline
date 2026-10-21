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
bash run.sh          # 默认：最多处理 200 个，每批 5 个塞 CLI
bash run.sh 30 3     # 语义同 run_bulk_v2.sh：<总项目数> <每CLI任务数>
```

`run.sh` 会依次执行：git pull → init_db → 跨天任务迁移 → Stage 3 语义过滤 → Stage 2 调度（incremental，仅一次）→ Stage 4 批量循环（analyze.py 生成 draft → analyze_v2.md 精炼，每批一次 CLI，失败 60s/180s 退避重试）→ Stage 4.5 评分 → Stage 5 生成报告 → git commit/push。

### 存量机会点再验证（v3）

```bash
bash run_verify_backlog.sh        # 默认：每批 20 条、总预算 100 条
bash run_verify_backlog.sh 20 200
```

`.env` 新增开关：`ANALYZE_PROMPT_VERSION`（v2 默认 / v3 启用升级版精炼+对抗验证+机器核账）、`VERIFY_MAX_PER_RUN`（默认 50）、`VERIFY_BATCH_SIZE`（默认 20）。

**灰度期防污染纪律**：v3 的 verify/validate 与 v2 共用同一张 opportunities 表，灰度期**同一天同一 DB 只允许跑一个版本**（跑 v3 的日子不用 run_bulk_v2.sh 跑 v2，反之亦然），否则对照组数据被污染。

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
| Stage 4.7 Verify | `prompts/verify_v3.md` + LLM → `stages/verify_ingest.py` | 本地 | 对抗验证：独立会话反驳 open 高/中价值机会点，裁决经脚本校验落 `data/verify_log/` |
| Stage 4.8 Validate | `stages/validate.py` | 本地 | 机器核账：API 验证 issue/PR/URL/label 真伪，伪证据剥离或 refuted |
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
- **禁止在脚本运行期间修改 `run.sh` / `run_bulk*.sh` / `run_verify_backlog.sh`**：bash 按字节偏移增量读取脚本，中途改文件会让它从错误位置续读。2026-10-19 实测：把两处 `100` 改成 `20`（文件短了 2 字节），跑到脚本末尾时 bash 从注释行 `# 3.5 v3: …` 的第 3 个字符开始读，把 `3.5` 当命令执行，Stage 3.5/4.5/5 与 push 全部没跑。改 `prompts/*.md` 和 `stages/*.py` 是安全的（前者按批渲染成临时文件，后者一次性读入），只有 shell 脚本有这个问题。
- **`scripts/` 目录是临时产物**：LLM 运行时可能生成临时脚本，已加入 `.gitignore`，不需要版本追踪。
- **测试**：`tests/` 下有 unittest 烟雾测试（`python3 -m unittest discover -s tests`），验证另靠各 stage 的 `--dry-run`、SQLite 查询以及报告内容检查。
- **find → verify 双阶段**：分析（find）与验证（verify）在不同 LLM 会话，验证者看不到分析推理、默认立场为反驳；验证状态复用 opportunities.status 枚举（verified/refuted），验证理由写 JSONL 日志不进 DB（零 DDL）。
- **welcome label 判定只有一份实现**：`stages/scoring.py` 的 `is_welcome_label()` 是唯一判定入口，`stages/analyze.py` 直接 `from stages.scoring import is_welcome_label`——生产者不能比消费者窄，两边各写一份必然漂移（2026-10-20 前就是这样：消费者学会了归一化装饰写法，生产者没学，8 条真实欢迎标签被漏掉）。导入必须走 `stages.scoring` 这条路径，导入成顶层 `scoring` 会加载出第二份独立副本。归一化只做**装饰**（emoji、命名空间前缀、连字符、单复数），且只对「明确欢迎措辞」开放；`enhancement` / `feature-request` / `accepted` 这类**报告者常自贴**的弱信号只做精确匹配，否则 `type: enhancement` / `⭐ enhancement` 会集体伪装成 welcoming 并被 `score_value` 提升一档。
- **judge 写回的 `welcome_labels` 只放欢迎类 label**，不放该 issue 的完整 label 列表。2026-10-20 实测 783 行的 `welcome_labels` 里装的是 `feature` / `bug` / `question` / `triage` 之类——那是分类标签，不是欢迎标签。这条约束现在**由机器层强制**：`stages/validate.py` 已经拿到了 issue 的真实 label 列表，除了剥离**不存在的**（phantom）label，还用 `is_welcome_label` 剥离「存在但不是欢迎类」的 label（prompt 里同时保留说明，让 judge 少写垃圾）。
- **历史评分不追改**：`stages/scoring.py` 只处理 `value IS NULL` 的行，规则改了也不重算历史。
  2026-10-21 实测：624 行的 `maintainer_signal` 与现行规则重算结果不一致，其中 617 行带的是
  ≤365 天的 merged PR——即 5761b93 废除「近期 merged PR = welcoming」之前的旧规则输出。
  **按既定立场不追改**（merged-PR 噪音的修复落在信号生成处，不做历史降级）；
  它们会随 verify 复评逐步收敛。verify 阶段在 2026-10-21 自己也发现了这一系统性状态
  并同样没有借机改写。
  **但要分清「规则变了」与「数据被写坏了」**：后者（如 judge 违反 prompt 越权写评分列）
  要置 NULL 重算并留档 `data/rescore_log/`。两者的处置完全不同。
- **报告对「已验证但评级偏低」单独开一节**：上游表按 `value IN ('high','medium')` 过滤，`status='verified'` 且 `value='low'` 的行会被整类漏掉——那是「验证说好、规则说不值」的矛盾状态（2026-10-21 实测全库 22 条，占已验证行 2.6%）。`stages/report.py` 把它们放进「已验证但评级偏低的补充机会」章节，不混进高价值表。

