# Stage 4 深层分析任务执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:executing-plans 按任务逐步执行。

**Goal:** 对 2026-06-28 的 3 个待分析项目执行 Stage 4 深层分析，将结果写入 `analyses` 与 `opportunities` 表。

**Architecture:** 复用已存在的 `run_analysis.py` 实现，先快速审计关键规范点，再顺序执行 3 个项目，最后验证 DB 状态与机会点数量。

**Tech Stack:** Python 3, SQLite, GitHub REST API, `requests`

---

## 文件结构

- **现有脚本**: `run_analysis.py` — Stage 4 完整实现（约 39KB，未跟踪），负责读取 DB、调用 GitHub API、写入结果。
- **数据库**: `data/pipeline.db` — 含 `tasks`, `projects`, `analyses`, `opportunities`, `project_meta` 表。
- **环境配置**: `.env` — 已配置 `GITHUB_TOKEN`。
- **计划文档**: `docs/superpowers/plans/2026-06-28-stage4-deep-analysis.md` — 本文档。

---

## Task 1: 审查现有实现是否满足 Stage 4 规范

**Files:**
- Read: `run_analysis.py`

- [ ] **Step 1: 检查核心 API 调用方式**

确认 `run_analysis.py` 中以下调用使用 `params=` 传参：
- `GET /repos/{owner_repo}/issues`：`params={"state": "open", "sort": "comments", "direction": "desc", "per_page": 20}`
- `GET /repos/{owner_repo}/git/trees/HEAD`：`params={"recursive": 1}`
- `GET /repos/{owner_repo}/issues/{n}/timeline`：`params={"per_page": 100}`
- `GET /search/issues`：`params={"q": ..., "per_page": 10}`

- [ ] **Step 2: 检查 canonical_url 与 peer_versions 处理**

- canonical_url 为 NULL/unknown/N/A/−/−/null 或非 http 开头时，Step 3 跳过，gap 填 `canonical_url 未知，无法对比`。
- peer_versions 使用 `json.loads()` 解析，失败时打印 WARN 并跳过。

- [ ] **Step 3: 检查 evidence JSON 结构**

确认写入字段包含：
- `value_evidence.canonical_impl_url`, `value_evidence.peer_impl_urls`, `value_evidence.issue_reactions`
- `difficulty_evidence.canonical_impl_url`, `difficulty_evidence.canonical_impl_loc`, `difficulty_evidence.why_hard`
- `urgency_evidence.cve_id`, `urgency_evidence.has_prod_signal`, `urgency_evidence.has_workaround`
- `maintainer_evidence.similar_prs`, `maintainer_evidence.maintainer_responses`, `maintainer_evidence.welcome_labels`

---

## Task 2: 执行 Stage 4 分析

**Files:**
- Run: `python run_analysis.py`

- [ ] **Step 1: 确认环境变量**

```bash
cd /Users/lijianhua04/Documents/my-agents/catpawDesk-workspace/github-opportunities/opensource-project-opportunities-pipeline
source .env
python -c "import os; print('TOKEN SET:', bool(os.environ.get('GITHUB_TOKEN')))"
```

Expected: `TOKEN SET: True`

- [ ] **Step 2: 运行分析脚本**

```bash
python run_analysis.py
```

Expected: 脚本顺序处理 `graphql-editor/graphql-zeus`, `apache/burr`, `alibaba/SREWorks`，每个项目输出 `Done: ... with N opportunities, overall_score=X`，无未捕获异常。

- [ ] **Step 3: 记录运行日志**

将标准输出保存到 `data/stage4_2026-06-28.log`，便于后续排查：

```bash
python run_analysis.py | tee data/stage4_2026-06-28.log
```

---

## Task 3: 验证写入结果

**Files:**
- Query: `data/pipeline.db`

- [ ] **Step 1: 检查 tasks 状态**

```bash
sqlite3 data/pipeline.db "SELECT id, project_id, task_type, status, started_at, finished_at FROM tasks WHERE task_date = '2026-06-28';"
```

Expected: 3 条记录 status 均为 `done`，且 `finished_at` 有值。

- [ ] **Step 2: 检查 analyses 表**

```bash
sqlite3 data/pipeline.db "SELECT project_id, overall_score, canonical_gap FROM analyses WHERE task_id IN (SELECT id FROM tasks WHERE task_date = '2026-06-28');"
```

Expected: 3 条 analysis 记录，`overall_score` 在 1~10 之间，`source_structure` 为合法 JSON。

- [ ] **Step 3: 检查 opportunities 表**

```bash
sqlite3 data/pipeline.db "SELECT project_id, source_type, source_ref, title, issue_reactions, overall_score FROM opportunities o JOIN analyses a ON a.project_id = o.project_id WHERE a.task_id IN (SELECT id FROM tasks WHERE task_date = '2026-06-28') LIMIT 50;"
```

Expected: 每个项目不超过 10 条机会点；`value_evidence` / `difficulty_evidence` / `urgency_evidence` / `maintainer_evidence` 为合法 JSON。

---

## Task 4: 提交运行结果

**Files:**
- Add: `data/pipeline.db`, `data/stage4_2026-06-28.log`

- [ ] **Step 1: 检查 DB 变更**

```bash
git status
```

Expected: `data/pipeline.db` 已修改；新增日志文件；`run_analysis.py` 保持未跟踪（按项目约定）。

- [ ] **Step 2: 提交变更**

```bash
git add data/pipeline.db data/stage4_2026-06-28.log
git commit -m "feat: bulk analysis 2026-06-28 (done=3 skipped=0 remaining=0)"
```

Expected: 提交成功，消息格式与近期提交一致。

---

## 自我审查 (Self-Review)

1. **规范覆盖**: 复用脚本已覆盖 Step 1~7；本计划额外加入审查与验证步骤，确保输出质量。
2. **无占位符**: 所有步骤均含具体命令与预期输出。
3. **类型一致性**: 使用 `sqlite3` 查询验证字段类型与约束（`overall_score` 1~10）。

---

## 执行交接

**计划已保存至 `docs/superpowers/plans/2026-06-28-stage4-deep-analysis.md`。**

建议直接 **Inline Execution**：在当前会话中依次执行 Task 1 → Task 2 → Task 3 → Task 4。
