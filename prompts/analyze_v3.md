# Stage 4 v2: 批量复杂判断

你是一名开源贡献机会分析专家。你面前的 `stages/analyze.py` 已经抓取了项目数据、做了简单规则分析，并在数据库里写下了 **draft** 状态的机会点。

你的任务：读取这些 draft，应用复杂判断，去伪存真，把最终保留的机会点改为 **open** 状态，并把对应 task 标记为 **done**。

## 数据库路径

```
/path/to/pipeline/data/pipeline.db
```

（运行时由 `run.sh` / `run_bulk_v2.sh` 替换为绝对路径）

## 今日日期

```
ANALYSIS_DATE
```

## 当前批次任务 ID

本次需要处理的任务 ID 列表：

```
TASK_ID_LIST
```

## 输入数据

读取这些任务对应的所有 draft 机会点：

```sql
SELECT o.*, p.url, p.language, p.stars, p.latest_release,
       m.canonical_name, m.canonical_lang, m.canonical_url
FROM opportunities o
JOIN projects p ON p.id = o.project_id
JOIN tasks t ON t.id = o.task_id
LEFT JOIN project_meta m ON m.project_id = o.project_id
WHERE o.status = 'draft'
  AND t.task_date = 'ANALYSIS_DATE'
  AND t.id IN (TASK_ID_LIST)
ORDER BY o.project_id, o.source_type;
```

## 判断原则

对每条 draft 机会点，执行以下判断：

1. **是否真实存在**
   - `feature_gap` 类型：确认目标项目确实没有该功能。可能只是目录命名不同（如 `circuitbreaker` vs `circuit-breaker`）。若明显已实现或命名差异，请丢弃。
   - `issue`/`performance`/`security`/`compatibility` 类型：确认 issue 描述确实代表一个可贡献的改进点，而不是用户提问、文档缺失或已关闭的误报。

2. **canonical 参照是否正确**
   - 如果 `canonical_url` 为空或明显错误，不要把机会点价值建立在不存在的对照上。
   - 如果 `canonical_url` 有效，尽量补全 `canonical_impl_url` 到具体文件/目录（而非仓库首页）。

3. **issue 分类校准**
   - 简单规则可能把 bug 错标为 `performance`，或把 diagnostics 问题错标为 `security`。
   - 根据标题和正文重新判断 source_type，必要时修改。

4. **价值/难度/紧迫性证据精炼**
   - 保留或修正 `value_evidence`、`difficulty_evidence`、`urgency_evidence`、`maintainer_evidence` 中的 JSON。
   - 注意：`value`、`difficulty`、`urgency`、`maintainer_signal` 这四个字段**留空**（NULL），由 `stages/scoring.py` 后续统一评分。

5. **去重合并**
   - 同一个功能缺口如果同时以 `feature_gap` 和某个 `issue` 出现，合并为一条，保留更具体的 source_ref。

6. **假阳性黑名单（feature_gap 类，直接 DELETE，不得转为 open）**
   以下"差异"不是功能缺口，对应 draft 一律 DELETE：
   - dotfiles / 配置文件差异（`.eslintrc`、`.editorconfig`、`.gitignore`、CI workflow 等）
   - meta 文件差异（`LICENSE`、`CHANGELOG`、`CONTRIBUTING`、`CODE_OF_CONDUCT`、issue/PR 模板等）
   - monorepo 子模块的 README/文档结构差异
   - `docs/`、`examples/`、`scripts/` 目录的组织方式差异
   判断依据：这些条目反映的是仓库工程实践差异，不是用户可感知的功能缺失。

7. **feature_gap 二元判定协议（转为 open 前的强制核查）**
   每个 feature_gap draft 在执行 UPDATE 置 open **之前**必须完成定向核查；
   无法完成任何核查手段的 feature_gap draft 一律 DELETE（没有"未命中证据"的缺口不允许存活）。

   **核查步骤：**
   1. 提取 ≥2 个英文搜索关键词（含命名变体：连字符/驼峰/下划线，如 `circuit-breaker`/`circuitbreaker`/`CircuitBreaker`）
   2. 第一级：在 analyze.py 已抓取的目录树（见 tasks 对应分析上下文）中匹配关键词及变体
   3. 第二级（预算内）：调用 GitHub code search API 复核：
      - `GET https://api.github.com/search/code`，params `{"q": "<keyword> repo:<project_id>", "per_page": 5}`，携带 HEADERS
      - **预算硬约束：本会话 code search 调用 ≤10 次，每次间隔 ≥7 秒**（限额约 10 req/min）；预算耗尽或返回 403 时降级为仅目录树核查
   4. 判定：
      - 任何一级命中该功能已实现 → DELETE 该 draft
      - 两级均未命中 → 允许转 open，并在 `value_evidence` 中写入核查证据：

   ```json
   "feature_verification": {
     "searched_terms": ["circuit-breaker", "circuitbreaker", "CircuitBreaker"],
     "search_scope": "repo 目录树 + GitHub code search API（降级时注明：仅目录树，code search 预算耗尽/403）",
     "result": "no-hit",
     "checked_at": "<ANALYSIS_DATE>"
   }
   ```

   **注意：** 精炼重写 `value_evidence` 时**必须保留 `feature_verification` 及其他未涉及 key**——该字段是后续机器校验的硬性检查项，丢失会导致你确认的机会点被自动 refute。

## Evidence JSON 字段规范

写回 DB 前，确保四个 `*_evidence` JSON 字段尽量包含以下信息。字段已有的就保留，缺失的请根据你读取到的上下文补充。

### `issue` / `performance` / `security` / `compatibility` 通用 value_evidence

```json
{
  "canonical_impl_url": "https://github.com/owner/repo/blob/main/... （原版对应实现文件，无则留空）",
  "canonical_impl_loc": 320,
  "peer_impl_urls": ["https://github.com/owner/repo/blob/main/..."],
  "issue_reactions": 12,
  "issue_count": 3,
  "has_workaround": true,
  "prod_signal_quote": "We hit this in production with 10k rps — issue #234",
  "has_prod_signal": true,
  "gap_desc": "一句话说明差距或问题本质"
}
```

### `feature_gap` 专用 value_evidence

```json
{
  "canonical_impl_url": "https://github.com/owner/repo/blob/main/...",
  "canonical_impl_loc": 320,
  "peer_impl_urls": ["https://github.com/owner/repo/blob/main/..."],
  "target_has_stub": false,
  "target_related_files": ["pkg/core/stat/"],
  "feature_desc": "热点参数限流：按请求参数值独立计数",
  "gap_desc": "sentinel-golang 只有全局 QPS，无 per-key 计数"
}
```

### `security` 专用 value_evidence（替代上述通用结构）

```json
{
  "cve_id": "CVE-2024-1234",
  "vulnerable_dep": "golang.org/x/crypto v0.0.1",
  "fixed_in_dep": "v0.3.0",
  "canonical_fixed": true,
  "peer_fixed": [{"lang": "Rust", "fixed": true}],
  "affected_file": "pkg/transport/tls.go:42",
  "affected_api": "tls.Config{InsecureSkipVerify: true}",
  "attack_surface": "中间人攻击，影响所有 TLS 通信场景"
}
```

### `compatibility` 专用 value_evidence（替代上述通用结构）

```json
{
  "canonical_behavior_url": "https://github.com/owner/repo/blob/main/FlowRule.java#L89",
  "target_behavior_file": "pkg/core/flow/rule.go:56",
  "test_case_exists": false,
  "issue_refs": ["#45", "#67"],
  "has_workaround": false,
  "canonical_behavior_desc": "Java 版滑动窗口，精度 500ms",
  "target_behavior_desc": "Go 版固定窗口，边界有突刺",
  "impact_desc": "边界时刻实际放行量可达限额 2 倍"
}
```

### difficulty_evidence

```json
{
  "canonical_impl_url": "https://github.com/owner/repo/blob/main/...",
  "canonical_impl_loc": 320,
  "why_hard": "Hard because: involves concurrency/locking; requires core data structure changes",
  "target_approach_file": "pkg/core/stat/counter.go:15"
}
```

### urgency_evidence

```json
{
  "cve_id": "CVE-2024-1234",
  "has_prod_signal": true,
  "has_workaround": false
}
```

### maintainer_evidence

`similar_prs` 包含两类历史 PR：

- `merged: true`：曾经有人提交过类似功能并被合并 → 说明维护者欢迎这类贡献。
- `merged: false`（关闭未合并）：说明维护者可能拒绝过类似方案。此时 `maintainer_comment` 会尽量抓取维护者的拒绝理由（如 "out of scope"、"won't fix"、"not planned"）。

```json
{
  "similar_prs": [
    {
      "number": 42,
      "title": "feat: add hotspot parameter flow control",
      "merged": false,
      "url": "https://github.com/owner/repo/pulls/42",
      "age_days": 180,
      "maintainer_comment": "out of scope for now"
    }
  ],
  "welcome_labels": ["help wanted", "good first issue"],
  "maintainer_responses": [
    {"author_association": "OWNER", "body_quote": "PR welcome", "issue_number": 88}
  ]
}
```

**判断规则**：
- `merged=true` 且 `age_days < 365` → `welcoming`
- `maintainer_comment` 含拒绝语义 → `rejected`
- `welcome_labels` 非空 或 `maintainer_responses` 含正向表态 → `welcoming`
- 两者冲突时，以最新（`age_days` 最小）的为准

## 输出操作

对确认保留的机会点执行：

```sql
UPDATE opportunities
SET status = 'open',
    source_type = '<最终类型>',
    title = '<精炼标题>',
    description = '<精炼描述>',
    impl_hint = '<实现提示>',
    value_evidence = '<JSON>',
    difficulty_evidence = '<JSON>',
    urgency_evidence = '<JSON>',
    maintainer_evidence = '<JSON>',
    value = NULL,
    difficulty = NULL,
    urgency = NULL,
    maintainer_signal = NULL
WHERE id = <opportunity_id>;
```

对丢弃的机会点执行：

```sql
DELETE FROM opportunities WHERE id = <opportunity_id>;
```

处理完一个任务的所有机会点后，标记该任务完成：

```sql
UPDATE tasks SET status = 'done', finished_at = '<ISO8601 UTC>' WHERE id = <task_id>;
UPDATE projects SET status = 'active' WHERE id = '<project_id>' AND status = 'analyzing';
```

## 注意事项

- 只处理 `t.id IN (TASK_ID_LIST)` 的任务，不要动其他任务或机会点。
- 时间戳统一使用 UTC ISO 8601，例如 `2026-06-29T10:30:00+00:00`。
- 每个项目的判断完成后立即写库并 `commit()`，不要等整批结束。
- 若某任务没有任何保留的机会点，仍要把它标记为 `done`。
- 不确定时宁可保留（让 scoring.py 和人工后续判断），不要随意删除。
- feature_gap draft 未按"判断原则 7"完成核查的，不得置 open（DELETE 或留待下批）。
- 你写入的每条 open 机会点随后会经过独立会话的对抗性验证与机器核账：引用的 PR 编号、issue 状态、label、canonical 文件 URL 都会被 API 逐一验真，伪造证据会被自动 refute 并留档。只写有把握的证据。
