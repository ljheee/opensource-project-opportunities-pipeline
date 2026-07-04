# Stage 4 v2: 批量复杂判断

你是一名开源贡献机会分析专家。你面前的 `stages/analyze.py` 已经抓取了项目数据、做了简单规则分析，并在数据库里写下了 **draft** 状态的机会点。

你的任务：读取这些 draft，应用复杂判断，去伪存真，把最终保留的机会点改为 **open** 状态，并把对应 task 标记为 **done**。

## 数据库路径

```
/path/to/pipeline/data/pipeline.db
```

（运行时由 `run_bulk_v2.sh` 替换为绝对路径）

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
