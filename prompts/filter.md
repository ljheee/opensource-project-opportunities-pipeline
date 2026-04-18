# Stage 3: 语义过滤任务

你是一个开源项目分析专家。请按以下步骤处理 SQLite 数据库中待过滤的项目。

## 数据库路径

```
/path/to/pipeline/data/pipeline.db
```

（运行时由 run.sh 将此占位符替换为绝对路径）

## 输入

读取待过滤的项目（每次最多处理 100 个，避免超出上下文窗口）：

```sql
SELECT p.id, p.name, p.url, p.language, p.stars, p.description, p.topics, p.source
FROM projects p
JOIN project_meta m ON m.project_id = p.id
WHERE m.filter_status = 'pending'
ORDER BY p.stars DESC
LIMIT 100;
```

**字段说明**：`p.topics` 是数据库中存储的 **JSON 字符串**（如 `'["microservices","rate-limiting"]'`），若需按元素遍历，**必须先调用 `json.loads()` 解析为 Python 列表**；若解析失败（`json.JSONDecodeError`），将其视为空列表 `[]`，不影响后续过滤判断。**不可直接遍历原始字符串**（字符串遍历会逐字符迭代，无法匹配 topic 名称）。

## 过滤规则（按顺序判断，命中即 skip）

**跳过条件（filter_status = 'skip'）：**

1. **护城河判断**：该项目本身就是原版（Kafka、Redis、MySQL 本体）；已是所在领域当前语言的事实标准（zerolog、resty、pgx）；生态依赖极深（coredns、etcd、containerd）
2. **项目性质**：纯 CLI 工具（无库/服务组件属性）；纯示例/教程/脚手架；纯资源列表/awesome 系列；商业产品的开源 SDK/Agent
3. **场景限制**：游戏专用框架；区块链/Web3 专用；K8s 基础设施层（非应用层组件）；IoT 专用平台

**保留条件（filter_status = 'keep'）——以下三条必须同时满足：**

1. **有明确原版**：是某个知名原版（Java/Python/C++/Scala）的其他语言移植版或替代实现；**原创项目（无法对应到任何已有原版）一律 skip**
2. **存在功能缺口**：原版功能集丰富，当前语言版本存在明显功能差距
3. **有真实用户群体**：stars >= 300，有 open issues 活动

## 输出

对每个项目执行以下 SQL（注意：`project_meta.filter_status` 用 `skip`/`keep`，`projects.status` 用 `filtered_skip`/`bulk_pending`，两张表枚举值不同，不要混用）：

**跳过时：**
```sql
UPDATE project_meta
SET filter_status = 'skip',
    filter_reason = '<具体原因>',
    filtered_at   = '<ISO8601 时间>'
WHERE project_id = '<id>';

UPDATE projects
SET status = 'filtered_skip'
WHERE id = '<id>' AND status = 'discovered';
```

**保留时：**
```sql
UPDATE project_meta
SET filter_status    = 'keep',
    filter_reason    = '<保留理由>',
    canonical_name   = '<原版项目名，如 Apache Sentinel；若为原创项目无明确原版则填 NULL>',
    canonical_lang   = '<原版语言，如 Java；原创项目填 NULL>',
    canonical_url    = '<原版代码仓库首页 URL（GitHub/GitLab/ASF GitBox 均可），如 https://github.com/alibaba/Sentinel；原创项目或无法确定原版时填 NULL>',
    canonical_stars  = <原版 stars 数（用于报告展示，analyze.md 不读取此字段；原创项目填 NULL）>,
    peer_versions    = '<JSON: [{"lang":"Rust","url":"https://github.com/owner/repo","stars":1200}]；无其他语言版本时填 NULL>',
    filtered_at      = '<ISO8601 时间>'
WHERE project_id = '<id>';

UPDATE projects
SET status = 'bulk_pending'
WHERE id = '<id>' AND status = 'discovered';
```

> **`peer_versions` 字段说明**：`analyze.md` 只读取每个元素的 `url` 字段（用于 WebFetch peer 版本 README）；`stars` 字段保留供未来扩展，可选填写；**不要填写 `completeness_hint` 字段**（该字段已废弃，不被任何下游步骤读取，填写只会浪费 token）。

## 注意事项

- **时间戳格式**：所有 `filtered_at` 时间戳统一使用 **UTC ISO 8601 格式**，如 `2026-04-17T10:30:00+00:00`（含时区偏移 `+00:00`），不使用本地时区。Python 获取方式：`datetime.now(timezone.utc).isoformat()`（需 `from datetime import datetime, timezone`）。
- 无法访问项目页面时，执行以下两条 SQL（与"跳过时"模板相同，必须同时更新两张表），然后继续下一个：
  ```sql
  UPDATE project_meta SET filter_status = 'skip', filter_reason = 'fetch_failed', filtered_at = '<ISO8601 时间>' WHERE project_id = '<id>';
  UPDATE projects SET status = 'filtered_skip' WHERE id = '<id>' AND status = 'discovered';
  ```
- 不确定时偏向保留（keep），宁可多分析一个
- 每处理完一个项目立即写库，**必须在每个项目的两条 UPDATE 执行后立即调用 `conn.commit()`**，不要批量等待——Python `sqlite3` 的 `execute()` 不会自动持久化，未 commit 的写入在 `conn.close()` 时会被回滚丢失
- **SQL 执行方式**：优先使用 Python `sqlite3` 模块的**参数化查询**（`conn.execute("UPDATE project_meta SET filter_status=? WHERE project_id=?", (status, pid))`），完全避免引号转义问题。只有在无法使用参数化查询时才手动拼接 SQL 字符串。
- **SQL 单引号转义**（仅在必须字符串拼接时）：将所有文本字段（`filter_reason`、`canonical_name` 等）中的单引号 `'` 替换为 `''`（两个单引号）再嵌入 SQL，防止语法错误（如 `Cap'n Proto` → `Cap''n Proto`）
- **双引号不需要转义**：`peer_versions` 是 JSON 字符串，JSON 内部的双引号 `"` 嵌入 SQL 单引号字符串时**不需要**任何转义，直接写 `'[{"lang":"Rust","url":"..."}]'` 即可；错误地将 `"` 写成 `\"` 或 `""` 会导致 `json.loads()` 解析失败
