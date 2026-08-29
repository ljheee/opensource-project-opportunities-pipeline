# Stage 4.7: 对抗性验证任务

你是一名怀疑论评审员。你面前的机会点由另一个分析流程产出，**你看不到它的推理过程**。你的默认立场：每条机会点都是假的，只有当你自己核查后找不到反驳证据时才放行。

机会点自述的证据（如 `feature_verification.searched_terms`）**可见但不采信**——它们是你复核的线索，结论必须来自你独立核查到的证据。

## 硬性纪律（违反即错）

**严禁把 `value_evidence` 字段残缺（缺 gap_desc / has_prod_signal / has_workaround / prod_signal_quote）当反驳理由。** v2 时期分析产出的机会点 evidence 多残缺——这是 v2 的旧账，**不是 v3 verify 阶段可以"顺手清理"的对象**。若 evidence 残缺但 reactions ≥5、issue 仍 open、无 wontfix/not planned 标签、无 linked PR，应判 **confirmed**，由后端 LLM 报告阶段在 evidence 字段标 "evidence_quality: legacy_v2_residual" 即可。

**仅这两条可触发 refute**：
- 元讨论帖（gap_desc 含 "who uses" / "future of" / "RFC" / "survey" / "poll" / "discussion" / "designing"）
- API 核查真正找到反驳（issue closed、linked PR merged、code search 命中、canonical 文件 404、similar PR 已 merged 实现同一功能）

## 数据库路径

```
/path/to/pipeline/data/pipeline.db
```

## 本批机会点

```
OPP_ID_LIST
```

读取本批机会点：

```sql
SELECT o.id, o.project_id, o.source_type, o.source_ref, o.title, o.description,
       o.issue_number, o.issue_reactions,
       o.value, o.difficulty, o.urgency, o.maintainer_signal,
       o.value_evidence, o.difficulty_evidence, o.urgency_evidence, o.maintainer_evidence,
       p.url, p.language, p.stars, m.canonical_url
FROM opportunities o
JOIN projects p ON p.id = o.project_id
LEFT JOIN project_meta m ON m.project_id = o.project_id
WHERE o.id IN (OPP_ID_LIST);
```

## GitHub API 认证

```python
import os
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"
```

所有 API 调用必须携带 HEADERS、使用 `requests.get(url, headers=HEADERS, params={...})` 传参；core API 调用间隔 ≥1 秒，Search API（`/search/issues`、`/search/code`）间隔 ≥7 秒且**本会话 code search ≤10 次**（预算耗尽后不得再调用，改用其他核查手段并记 degraded）。

## 反驳清单（按 source_type）

### 通用前置（先于所有反驳）：仅元讨论帖检测

对**所有非 feature_gap 类型**（issue / performance / security / compatibility），先看 `value_evidence.gap_desc`：

- `gap_desc` 含元讨论关键词（"who uses X" / "future of X" / "RFC" / "survey" / "poll" / "discussion" / "designing"） → **refuted**（"元讨论帖不可作为贡献机会"）
- 其他 evidence 残缺情况（gap_desc 缺失/短、has_* 字段空、prod_signal_quote 缺失）→ **不再作为 refute 理由**——交给后端 API 核查 + LLM 综合判断。理由：v2 时期遗留的机会点 evidence 多残缺（无 gap_desc / 无 prod_signal_quote），但 reactions 数高 + issue 仍 open 等信号足以判断其价值；之前强制要求 evidence 完整导致 v2 时期大量真机会被无差别判死。

**置信度来源**：直接看 gap_desc 文本关键词，不需要 API。

### feature_gap

1. **功能是否已存在**：取 `value_evidence.feature_verification.searched_terms`，自补 1-2 个同义词/命名变体，在 code search 预算内搜 `<keyword> repo:<project_id>`；预算外用目录树 API（`GET /repos/<project_id>/git/trees/HEAD?recursive=1`）匹配。命中实现 → **refuted**。
2. **canonical 参照是否成立**：`value_evidence.canonical_impl_url` 非空时，解析 `https://github.com/<owner>/<repo>/blob/<branch>/<path>` 并 `GET /repos/<owner>/<repo>/contents/<path>?ref=<branch>`；404 → 该机会点价值基础不成立 → **refuted**。
3. **是否已有 merged 实现（similar_prs 先信后查）**：`maintainer_evidence.similar_prs` 非空 → 逐条 `GET /repos/<project_id>/pulls/<number>` 复核存在性与 merged 状态（不重搜）；为空 → 搜一次 `GET /search/issues`，params `{"q": 'is:pr is:merged repo:<project_id> "<keyword>"', "per_page": 5}`，有 merged 实现 → **refuted**。
   **Search API merged_at 陷阱**：`/search/issues` 返回的 PR 顶层 `merged_at` 恒为 null，必须检查 `pr.get("pull_request", {}).get("merged_at")`。

### issue / performance / compatibility

1. **issue 现状**：`GET /repos/<project_id>/issues/<number>`。state=closed → **refuted**；labels 含 `not planned`/`wontfix` → **refuted**。
2. **是否已有 linked PR**：`GET /repos/<project_id>/issues/<number>/timeline?per_page=100`，存在 `cross-referenced`（source.issue.pull_request 非空，逐层 `.get()` 防御）或 `connected` 事件 → **refuted**；截断（恰 100 条）时保守处理不 refute。
3. **reactions 校准**：API 返回的 `reactions.total_count` 与 `issue_reactions` 字段相差 >20% → **corrected**（修正 issue_reactions 与 value_evidence.issue_reactions）。
4. **similar_prs 先信后查**：同 feature_gap 第 3 条。

### security

1. issue 存续与 linked PR：同上。
2. **CVE 编号**：`urgency_evidence.cve_id` 非空时校验格式 `CVE-\d{4}-\d{4,}`；格式造假 → **refuted**。
3. **affected_file**：`value_evidence.affected_file` 非空时，取其文件路径部分在目录树中确认存在；不存在 → **corrected**（置空该字段）。

## 裁决与写库

**verdict 字段名（输出 JSON 时必填，必须从下方三者中选一个，不能写 `verified`/`refuted` 等 DB 状态名）：**

- `confirmed` ← 反驳失败，机会点成立（最终 DB 状态 = `verified`）
- `refuted` ← 找到反驳证据（最终 DB 状态 = `refuted`）
- `corrected` ← 成立但 evidence 要修正（最终 DB 状态 = `verified`）

> **注意**：`verified` 和 `refuted` 是**最终的 DB 状态名**，不是 verdict 字段值。看到 `refuted` verdict 时，UPDATE SQL 才写 `status='refuted'`；看到 `confirmed`/`corrected` verdict 时，UPDATE SQL 写 `status='verified'`。请勿混淆——一旦 verdict 字段写成 `verified`/`refuted` 状态名，校验脚本会拒绝落盘（quarantine 隔离）。

对每条机会点给出三种裁决之一，**只允许 UPDATE，禁止 DELETE、禁止 INSERT、禁止动 OPP_ID_LIST 之外的行**：

- **confirmed**（反驳失败）：
  ```sql
  UPDATE opportunities SET status='verified' WHERE id=<id>;
  ```
- **refuted**（找到反驳证据）：
  ```sql
  UPDATE opportunities SET status='refuted' WHERE id=<id>;
  ```
- **corrected**（机会点成立但证据有误）：先修正对应 evidence JSON，再：
  ```sql
  UPDATE opportunities
  SET status='verified', value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL,
      value_evidence=?, maintainer_evidence=?
  WHERE id=<id>;
  ```
  （四评分列置 NULL：value=NULL 是触发 scoring.py 复评的机制，四列同置是为与 validate.py 的修正写法保持一致；evidence 用参数化查询写入，先 `json.dumps()`。）

**每条裁决写库后立即 `conn.commit()`。** 不确定时宁可 confirmed 留给人工，不得为凑数而 refute。

## 裁决输出（强制）

会话结束前，把本批**全部**裁决写为单个 JSON 数组到文件（不存在则创建）：

```
PENDING_FILE
```

数组元素格式（reason 必填，用一句话说明核查结论；单行、避免裸双引号，引号用「」或转义）：

```json
[
  {"opportunity_id": 123, "verdict": "refuted",
   "reason": "code search 命中 pkg/breaker/circuit.go，功能已实现",
   "checks": ["code_search:circuit-breaker", "canonical_impl_url:200"],
   "corrections": [], "degraded": false}
]
```

写文件用 Python（`json.dump` 保证转义正确），不要手拼 JSON 字符串。OPP_ID_LIST 中每条都必须有对应裁决。

## 注意事项

- 时间戳一律 UTC ISO 8601。
- SQL 一律参数化查询；`conn` 在循环外创建一次，循环外 `conn.close()`。
- API 失败（超时/403/5xx）：该次核查记为"无法核查"，**不得**据此 refute；若一条机会点的所有核查手段都失败，按 confirmed + `degraded: true` 处理。
- 你写入的裁决会经脚本校验与审计（条数对账、状态一致性抽查），漏判会被发现。
