# Stage 4: 深层分析任务

你是一个开源贡献机会分析专家，擅长识别"原版（Java/Python）已实现某功能，但其他语言移植版尚未实现或实现较差"的贡献机会。

## 数据库路径

```
/path/to/pipeline/data/pipeline.db
```

（运行时由 run.sh 将此占位符替换为绝对路径）

## 今日日期

```
ANALYSIS_DATE
```

（运行时替换）

## GitHub API 认证

所有 GitHub REST API 调用**必须**携带以下请求头：
```
Accept: application/vnd.github+json
Authorization: Bearer <GITHUB_TOKEN 环境变量的值>
```

调用前**必须**按以下方式构造 HEADERS（`Accept` 头是必须项，不可省略；缺少 `Accept` 头时 GitHub 不保证返回 `reactions` 等扩展字段）：

```python
import os
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"
```

若 `GITHUB_TOKEN` 为空，仍可调用但限额仅 60 req/hour，Search API 会直接返回 403——遇到 403 时按 API 错误处理原则处理（Step 6/6.5 的 403 → 跳过该 issue/PR；Step 2 核心 API 的 403 → 中止任务并回滚）。

## 输入

读取今日待分析任务：

```sql
SELECT t.id as task_id, t.project_id, t.task_type, t.trigger_reason,
       p.url, p.language, p.stars, p.latest_release,
       m.canonical_name, m.canonical_lang, m.canonical_url,
       m.peer_versions
FROM tasks t
JOIN projects p ON p.id = t.project_id
LEFT JOIN project_meta m ON m.project_id = t.project_id
WHERE t.task_date = 'ANALYSIS_DATE'
  AND t.status IN ('pending', 'running')
ORDER BY
  CASE t.task_type WHEN 'triggered' THEN 0 WHEN 'incremental' THEN 1 ELSE 2 END,
  p.stars DESC;
```

## 每个项目的分析流程

对每个任务，按以下步骤执行：

### Step 1: 标记开始

```sql
UPDATE tasks   SET status = 'running',  started_at  = '<now>' WHERE id = <task_id>;
UPDATE projects SET status = 'analyzing'                        WHERE id = '<project_id>' AND status IN ('active', 'bulk_pending');
```

### Step 2: 抓取目标项目信息

- GitHub API: `GET /repos/<project_id>/readme`（需携带 HEADERS）— 获取项目 README（响应中 `content` 字段为 base64 编码，用 `base64.b64decode(resp["content"]).decode("utf-8", errors="replace")` 解码）；提取功能列表
- GitHub API: `GET /repos/<project_id>/releases?per_page=5`（需携带 HEADERS）— 读取最近 5 个发布说明
- GitHub API: `GET /repos/<project_id>/issues?state=open&sort=comments&direction=desc&per_page=20`（需携带请求头 `Accept: application/vnd.github+json` 以确保响应包含 `reactions` 字段）— top 20 高讨论度 issue（Issues API 不支持 sort=reactions，用 comments 近似；拿到后按 `issue.get("reactions", {}).get("total_count", 0)` 降序重排，`reactions` 字段或 `total_count` 子字段缺失时视为 0）；**注意：GitHub Issues API 默认同时返回 issue 和 PR，需过滤掉含 `"pull_request"` 键的条目，只保留纯 issue**；**必须使用 `requests.get(url, headers=HEADERS, params={"state": "open", "sort": "comments", "direction": "desc", "per_page": 20})` 传参，不可手动拼接 URL 查询字符串**
- GitHub API: `GET /repos/<project_id>/git/trees/HEAD?recursive=1` — 完整目录结构（若响应体中 `"truncated": true`，则只保留 `tree` 数组中 `path` 不含 `/` 的条目，即只保留根目录层级的条目——包括根目录下的文件（`type=blob`，如 `go.mod`、`README.md`）和根目录下的子目录名（`type=tree`，如 `src`、`pkg`、`cmd`），不包含子目录内容）；**必须使用 `requests.get(url, headers=HEADERS, params={"recursive": 1})` 传参**

### Step 3: 抓取原版信息

- 若 `canonical_url` 为 NULL、空字符串、或非 URL 占位符（字符串值为 `"unknown"`、`"N/A"`、`"—"`、`"-"`、`"null"` 等，即不以 `http` 开头），跳过本步骤及 Step 4，`canonical_gap` 填 "canonical_url 未知，无法对比"，`peer_comparison` 填 "—"；此时 Step 7 中所有机会点的 `value_evidence.canonical_impl_url` 和 `difficulty_evidence.canonical_impl_url` **必须填空字符串 `""`**（不可填 canonical_url 本身或目标项目的文件 URL——scoring.py 以空字符串判定"无参考实现"，填入任何非空 URL 均会导致 value/difficulty 错误上调）
- 从 `canonical_url` 解析出 `<canonical_owner>/<canonical_repo>`（如 `https://github.com/alibaba/Sentinel` → `alibaba/Sentinel`）
- GitHub API: `GET /repos/<canonical_owner>/<canonical_repo>/readme`（需携带 HEADERS）— 获取原版 README（base64 解码），提取原版功能全集（feature matrix）
- GitHub API: `GET /repos/<canonical_owner>/<canonical_repo>/git/trees/HEAD?recursive=1`（需携带 HEADERS）— 获取原版完整目录结构
- **必须定位每个核心功能的实现文件**：在目录结构的 `tree` 数组中搜索路径含功能关键词的文件（如 `RateLimiter`、`CircuitBreaker`、`Scheduler`、`Cache`）；找到后读取 `default_branch`（调用 `GET /repos/<canonical_owner>/<canonical_repo>` 的 `default_branch` 字段）并构造文件 URL：`https://github.com/<canonical_owner>/<canonical_repo>/blob/<default_branch>/<path>`；**无法定位具体文件时才填空字符串**，不可直接填仓库首页 URL

### Step 4: 横向对比其他语言版本

- 若 `peer_versions` 为 NULL、空字符串或字面量 `"null"`，跳过本步骤
- `peer_versions` 是数据库中存储的 JSON 字符串，**必须先调用 `json.loads()` 解析为 Python 列表**；若解析失败（`json.JSONDecodeError`），**打印警告** `WARN: peer_versions JSON 解析失败，project_id=<project_id>，原始值=<peer_versions>` 并跳过本步骤；若解析后为空数组，直接跳过本步骤。**不可跳过 `json.loads()` 直接遍历原始字符串**（字符串遍历会产生单个字符而非 dict，导致 `AttributeError`）
- 遍历解析后的数组时，若某个元素不是 dict（例如解析结果为嵌套字符串），跳过该元素并打印警告，继续处理后续元素
- WebFetch 各版本 `url` 字段对应的 README
- 判断：目标版本 vs 原版 vs 其他语言版本，谁更领先/落后
- 记录各语言版本的功能完整度估算（百分比）
- 对每个发现的机会点：将已确认实现该功能的 peer 版本文件 URL 填入 `value_evidence.peer_impl_urls`（无则填 `[]`）

### Step 5: 源码结构分析

- 对照目录结构，识别核心模块
- 发现原版有但目标版本完全缺失的模块（这是 feature_gap 类型机会的来源）
- **将发现的每个缺口暂存为结构化条目**，格式为 `(feature_name, canonical_lang, canonical_impl_url)`，例如 `("adaptive-throttling", "Java", "https://github.com/alibaba/Sentinel/blob/master/sentinel-core/src/main/java/com/alibaba/csp/sentinel/slots/block/flow/controller/WarmUpController.java")`；**在内存中维护这份列表，直到 Step 7 写库时使用**；Step 7 写库时须将每个条目转化为 `source_ref = canonical:<canonical_lang>/<feature-name>`（如 `canonical:Java/adaptive-throttling`），此列表即为 Step 7 中 feature_gap 机会点的唯一来源
  - `canonical_impl_url` **必须是原版仓库中实现该功能的具体文件 URL**（非仓库首页，非目录页）；在 Step 3 已获取的目录结构中搜索文件名含功能关键词的文件（如 `RateLimiter`、`CircuitBreaker`、`Scheduler`）；找不到具体文件时才填空字符串 `""`
  - `feature_name` 须连字符分隔且足够具体，确保在同一 `project_id` 内唯一；超过 4 段时取最核心 2 段
  - 若 `canonical_url` 未知（Step 3 已跳过），则 Step 5 不应产生 feature_gap 条目（无原版参照，无法确认缺口）
- **与 Step 6 issue 去重（仅限 feature_request 类 issue）**：若 Step 5 的某个 feature_gap 缺口与 Step 6 的某个 issue 描述的是**同一个缺失功能**（判断标准：issue 的核心诉求是"请求增加某功能"即 source_type 为 `issue`，且 issue 标题/正文中的功能名称与 feature_gap 名称语义相同，例如 issue 标题含 "add rate-limit support" 而 feature_gap 名为 "rate-limit"），则**合并为一条 feature_gap 记录**，并将该 issue 的 `issue_number` 和 `issue_reactions` 填入该 feature_gap 条目（而非丢弃），确保 scoring.py 能读到 reactions 数据进行 value 判断；该 issue 条目不再单独写库，避免同一功能产生两条记录。**注意以下情况不合并，需分别写库**：① issue 是 bug 报告（功能存在但有问题），而非功能缺失请求——bug 与 feature_gap 是不同维度的问题；② issue 描述的功能与 feature_gap 功能名称仅部分相关（如 issue 是 "rate-limit 在高并发下精度问题"，feature_gap 是 "rate-limit 功能缺失"），两者应分别记录

### Step 6: Issues 深度分析

- 逐条读取 top issues 正文（直接使用 Step 2 已获取并按 reactions 重排后的 issue 列表，**禁止在本步骤重新调用 Issues API**）；**每个 issue 的 `reactions.total_count` 必须从 Step 2 的响应数据中读取并记录**，Step 7 写库时填入 `issue_reactions` 字段（即使为 0 也必须显式填写，不可省略）
- 跳过：issue 已有关联 PR — 判断方法：GitHub API `GET /repos/<project_id>/issues/<issue_number>/timeline?per_page=100`（需携带请求头 `Accept: application/vnd.github+json`；**必须使用 `requests.get(url, headers=HEADERS, params={"per_page": 100})` 传参，不可手动拼接 URL 查询字符串**），满足以下任一条件则视为已有关联 PR（`has_linked_pr = 1`），跳过该 issue：
  1. 存在 `event=cross-referenced` 且 `source.get("issue")` 不为 null 且 `source["issue"].get("pull_request")` 不为 null 的条目（注意：`source` 结构为 `{"type": "issue", "issue": {...}}`；当 `source["type"]` 不是 `"issue"` 时 `source["issue"]` 键可能不存在，必须用 `.get()` 防御；即使 `source["issue"]` 存在，其中的 `pull_request` 键也可能不存在（普通 issue cross-reference），同样必须用 `.get()` 防御，禁止直接用 `source["issue"]["pull_request"]`）
  2. 存在 `event=connected` 的条目（PR 通过 Development 侧边栏显式关联）
  若响应数组长度恰好为 100（可能被截断），则保守地继续分析该 issue（`has_linked_pr = 0`），不跳过
- 分类 issue 类型，并对应到写库时的 `source_type`（若一个 issue 同时符合多个类型，按以下优先级取最高级：`security` > `performance` > `compatibility` > `issue`）：
  - `feature_request` 或 `bug` → `source_type = "issue"`
  - `performance`（性能问题）→ `source_type = "performance"`
  - `security`（安全漏洞/不安全 API）→ `source_type = "security"`
  - 跨语言/平台兼容性问题 → `source_type = "compatibility"`
- 对比：该功能原版是否已实现？其他语言版本是否已实现？


### Step 6.5: Maintainer 意图分析

- 对每个已识别的机会点（包括 feature_gap 和 issue 类型），提取 1-2 个核心关键词（**关键词必须是单词或连字符短语，不含空格**，多词用连字符连接，如 `rate-limit` 而非 `rate limit`）：
  - issue 类型：取 issue 标题中的核心英文词；若标题为中文（如"支持异步模式"），先将核心语义翻译为英文再提取关键词（如 `async-mode`），不直接使用中文字符（GitHub Search API 对非 ASCII 关键词的召回效果极差）
  - feature_gap 类型：取功能名称，如 "adaptive-throttling"、"rate-limit"；若功能名超过 4 个连字符段（如 `token-bucket-rate-limit-with-burst`），取最核心的 2 段（如 `token-bucket`）以提升召回率
  调用 GitHub Search API（**必须使用 `requests.get(url, params={"q": ..., "per_page": 10})` 传参，不可手动拼接 URL**，`params=` 会自动对双引号等特殊字符做 URL 编码，避免请求失败）：
  - URL: `https://api.github.com/search/issues`
  - params: `{"q": f'is:pr is:closed repo:{project_id} "{keyword}"', "per_page": 10}`
  - **关键词必须用英文双引号括起来**，防止 GitHub Search 将连字符 `-` 解析为 NOT 运算符，如 `rate-limit` 不加引号会被解析为 `rate AND NOT limit`；Search API 有 30 req/min 限制，每次调用后等待 2 秒
  - 若 Search API 调用失败，降级使用 `GET /repos/<project_id>/pulls?state=closed&per_page=50` 并手动过滤标题/描述含相关关键词的 PR
  搜索标题/描述含相关关键词的历史 PR，将符合条件的 PR 填入 `similar_prs` 数组：
  - 判断是否 merged（**API 差异注意**）：
    - Search API（`/search/issues`）返回的 PR 对象：顶层 `merged_at` 始终为 null，需检查 `pr.get("pull_request", {}).get("merged_at") is not None`；若 `pull_request` 键缺失（Search API 对某些 PR 不返回此子对象），`.get()` 返回 None，视为未合并
    - 降级 Pulls API（`/repos/.../pulls`）返回的 PR 对象：直接检查顶层 `pr["merged_at"] != null`
  - merged → `{"merged": true, "age_days": <从 merged_at 到今日的天数>, "maintainer_comment": ""}` （Search API 取 `pr.get("pull_request", {}).get("merged_at")`；若结果为 None，表示该 PR 实际未合并，按 closed without merge 处理。Pulls API 取 `pr["merged_at"]`）
  - `age_days` 计算**必须使用 UTC 时间**：`(datetime.now(timezone.utc) - datetime.fromisoformat(merged_at.replace("Z", "+00:00"))).days`（需 `from datetime import datetime, timezone`）；禁止使用 `datetime.now()` 本地时间，否则在非 UTC 机器上会有 0~1 天偏差
  - closed without merge：调用 `GET /repos/<project_id>/issues/<pr_number>/comments?per_page=100`，**仅**检查 `author_association` 为 `OWNER`/`COLLABORATOR`/`MEMBER` 的评论（即 maintainer 评论）是否含拒绝语义（"out of scope"/"won't fix"/"by design" 等）；不检查 PR body（body 是 PR 作者写的，不代表 maintainer 意见）
    - 含拒绝语义 → `{"merged": false, "age_days": <从 pr["closed_at"] 到今日的天数（两种 API 均在顶层；age_days 同样必须用 UTC now 计算）>, "maintainer_comment": "<引用原文>"}`
    - 无明确拒绝语义 → 不填入 `similar_prs`（scoring.py 无法从中提取信号，不要填充噪声数据）
- 对已有 issue 的 opportunity，调用 `GET /repos/<project_id>/issues/<issue_number>/comments?per_page=100`，检查 `author_association` 为 `OWNER`/`COLLABORATOR`/`MEMBER` 的 maintainer 回复：
  - 含 "PR welcome"/"good first issue"/"help wanted"/"contributions welcome" → 填入 `maintainer_responses`：`{"body_quote": "<引用原文>"}`
  - 含 "won't fix"/"out of scope"/"by design"/"not planned" → 填入 `maintainer_responses`：`{"body_quote": "<引用原文>"}`
  - 无明确表态 → 不填（不要填入无信号的评论）
- issue 上的 "help wanted"/"good first issue" 标签 → 填入 `welcome_labels` 数组
- 将收集到的原始数据填入 `maintainer_evidence` JSON，**不要填写信号判断结论**（scoring.py 会据此计算 `maintainer_signal` 和调整 value）
- 不要直接写入 `maintainer_signal` 或修改 `value` 字段，由 scoring.py 统一计算

### Step 7: 写入分析结果

> **机会点来源汇总**：写库前先整理本项目的全部机会点清单：
> - **feature_gap 条目**：来自 Step 5 暂存的 `(feature_name, canonical_lang)` 列表，逐一转化为 `source_type=feature_gap, source_ref=canonical:<lang>/<name>`
> - **issue 条目**：来自 Step 6 深度分析的 issue 列表（已按 Step 5 去重规则处理），`source_type=issue/security/performance/compatibility`
> - 两类条目合并后去重：仅当 feature_gap 与 feature_request 类型 issue 描述同一缺失功能时合并（保留 feature_gap 条目，将 issue 的 `issue_number`/`issue_reactions` 写入该条目）；bug 类 issue、security/performance/compatibility 类 issue 均不与 feature_gap 合并，独立写库

**Evidence JSON 结构（严格按以下 key 名填写，scoring.py 强依赖）：**

```
value_evidence:
  {"canonical_impl_url": "https://github.com/...", "peer_impl_urls": ["https://..."], "issue_reactions": 8}

difficulty_evidence:
  {"canonical_impl_url": "https://github.com/...", "canonical_impl_loc": 320, "why_hard": "needs core redesign"}
  （why_hard 若涉及以下情形，请在文本中包含对应关键词，以便规则引擎识别：
    核心数据结构变更 → 包含 "核心数据结构" 或 "core data structure"；
    并发/线程安全设计 → 包含 "并发设计" 或 "concurrency"；
    语言特性缺失 → 包含 "语言特性限制" 或 "language limitation"）

urgency_evidence:
  {"cve_id": null, "has_prod_signal": true, "has_workaround": false}
  （`has_prod_signal` / `has_workaround` **必须填 JSON 布尔值 `true` 或 `false`，或 JSON `null`**，
  **禁止填 "maybe"/"possibly"/"partial"/"unclear"/"unknown" 等模糊字符串**——scoring.py 会将这类
  字符串视为 `false`（无信号），错误地用模糊字符串可能导致紧迫度被低估。若确实无法判断，填 `false`）

maintainer_evidence:
  {"similar_prs": [{"merged": true, "age_days": 45, "maintainer_comment": ""}],
   "maintainer_responses": [{"body_quote": "pr welcome"}],
   "welcome_labels": ["help wanted"]}
```

- `canonical_impl_url`：原版实现该功能的具体文件 URL（非仓库首页）；**无法确定具体文件时填空字符串 `""`，不要填 "unknown"、"null" 或仓库首页 URL**（空字符串会被 scoring.py 识别为"无参考实现"，触发 difficulty=high）
- `peer_impl_urls`：其他语言版本实现同功能的文件 URL 列表，无则填 `[]`
- `issue_reactions`：issue 的 reactions 总数（`reactions.total_count`）；来自 issue 的机会点**必须填写**，与 `opportunities.issue_reactions` 列保持一致；**纯 feature_gap 类型（无对应 issue）填 `0`**（DB 列同样填 `0`，不填 NULL）；**由 feature_request issue 合并而来的 feature_gap 条目**（见 Step 5 去重规则），`value_evidence.issue_reactions` **须填该 issue 的实际 reactions 数**（不填 `0`），以便 scoring.py 正确判断 value=high
- `canonical_impl_loc`：原版实现文件的估算行数，无法确定填 `0`
- `has_prod_signal`：issue/PR 中是否有生产环境受影响的描述
- `similar_prs`：近一年内标题/描述与本机会相关的历史 PR（merged 或 closed）

**写入 analyses 表（先查后写，幂等）：**

先查询记录是否已存在：
```sql
SELECT COUNT(*) FROM analyses WHERE project_id = '<project_id>' AND task_id = <task_id>;
```

**`overall_score` 计算规则（INTEGER，必须在 1~10 之间，DB 有 CHECK 约束，超出范围会导致 INSERT 失败）：**

按以下规则从 `value/difficulty/urgency` 评分推算（此时 scoring.py 尚未运行，需根据 evidence 自行推算分值）：
- 基础分：`value=high` → 7，`value=medium` → 5，`value=low` → 3（取该项目所有机会点的最高 value）
- urgency=high → +1；urgency=low → -1
- difficulty=low → +1；difficulty=high → -1
- 无机会点（所有 issue 均跳过）→ 填 `5`（中性分）
- 最终结果必须夹到 `[1, 10]`：`max(1, min(10, score))`

若返回 0（不存在），执行 INSERT（**必须使用参数化查询**，`release_version` 参数传 Python 变量 `p.latest_release`，若其为 `None` 则参数化查询自动映射为 SQL NULL；禁止字符串拼接，否则 Python `None` 会变成字符串 `'None'` 写入 DB）：
```python
import json
source_structure_json = json.dumps(source_structure_dict)  # 必须先 json.dumps() 再传参；直接传 dict 会写入 Python repr 而非合法 JSON
conn.execute(
    "INSERT INTO analyses (project_id, task_id, analyzed_at, release_version, "
    "source_structure, canonical_gap, peer_comparison, overall_score) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    (project_id, task_id, now, p_latest_release,  # p_latest_release 为 None 时自动写 SQL NULL
     source_structure_json, canonical_gap_text, peer_comparison_text, overall_score)
)
```

若返回 > 0（已存在），执行 UPDATE 刷新（同样使用参数化查询，`release_version` 传 Python 变量，`None` 自动映射为 SQL NULL；`source_structure_json` 同样须先 `json.dumps()` 再传参）：
```python
conn.execute(
    "UPDATE analyses SET analyzed_at=?, release_version=?, source_structure=?, "
    "canonical_gap=?, peer_comparison=?, overall_score=? "
    "WHERE project_id=? AND task_id=?",
    (now, p_latest_release, source_structure_json,
     canonical_gap_text, peer_comparison_text, overall_score,
     project_id, task_id)
)
```

> **`source_structure` JSON 格式规范**：必须是合法 JSON 对象，格式为：
> `{"root_dirs": ["cmd", "pkg", "internal", "api"], "key_files": ["go.mod", "Makefile"], "notes": "monorepo，核心逻辑在 pkg/ 下"}`
> - `root_dirs`：根目录下的子目录名列表（string 数组）
> - `key_files`：根目录下的关键文件列表（string 数组，如 `go.mod`、`Cargo.toml`、`pyproject.toml`）
> - `notes`：补充说明，纯文字字符串，可为空字符串 `""`
> **禁止填纯文字描述（非 JSON 格式）**；若目录结构抓取失败，填 `{"root_dirs": [], "key_files": [], "notes": "目录结构获取失败"}`

**`source_ref` 格式规则（按 source_type）：**
- `issue` / `security` / `performance` / `compatibility`：填 issue URL，格式严格为 `https://github.com/<owner>/<repo>/issues/<number>`，不加尾部斜杠，不加查询参数
- `feature_gap`：填 `canonical:<lang>/<feature-name>`，如 `canonical:Java/adaptive-throttling`

`feature-name` 须足够具体（连字符分隔，如 `token-bucket-rate-limit` 而非 `rate-limit`），确保在同一 `project_id` 内唯一。

**增量任务防重复漂移**：若 `task_type` 为 `incremental` 或 `triggered`，在生成 `feature_gap` 类型的 `source_ref` 之前，**必须先查询**：
```sql
SELECT source_ref FROM opportunities
WHERE project_id = '<project_id>' AND source_type = 'feature_gap';
```
若已存在语义相同的功能缺口（如已有 `canonical:Java/rate-limit-token-bucket`），**必须沿用已有的 `source_ref`**，触发 UPDATE 而非 INSERT。禁止为同一功能缺口生成不同名称（如 `token-bucket-rate-limit`），否则会产生重复机会点记录。

**写入 opportunities 表（每个机会点，先查后写）：**

先查询记录是否已存在：
```sql
SELECT COUNT(*) FROM opportunities
WHERE project_id = '<project_id>' AND source_type = '<source_type>' AND source_ref = '<source_ref>';
```

若返回 0（不存在），执行 INSERT（**必须使用参数化查询**，同 analyses 表写法；所有文本字段含单引号时由参数化查询自动处理，无需手动转义）：
```python
import json
conn.execute(
    "INSERT INTO opportunities "
    "(project_id, task_id, source_type, source_ref, title, description, "
    "canonical_status, peer_status, impl_hint, "
    "issue_number, issue_reactions, has_linked_pr, "
    "value_evidence, difficulty_evidence, urgency_evidence, maintainer_evidence, "
    "status, first_seen_at, last_seen_at) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'open',?,?)",
    (project_id, task_id, source_type, source_ref,
     title, description, canonical_status, peer_status, impl_hint,
     issue_number,   # feature_gap 类型传 None（自动映射为 SQL NULL）
     issue_reactions,  # feature_gap 类型传 0（不传 None）
     has_linked_pr,  # 0 或 1
     json.dumps(value_evidence_dict),       # 必须先 json.dumps()
     json.dumps(difficulty_evidence_dict),  # 必须先 json.dumps()
     json.dumps(urgency_evidence_dict),     # 必须先 json.dumps()
     json.dumps(maintainer_evidence_dict),  # 必须先 json.dumps()
     now, now)
)
```

> value / difficulty / urgency / maintainer_signal 列**不在此处填写**，由 scoring.py 根据 evidence 字段自动计算。

若返回 > 0（已存在），执行 UPDATE 刷新所有字段并触发重算（同样使用参数化查询）：
```python
conn.execute(
    "UPDATE opportunities "
    "SET title=?, description=?, canonical_status=?, peer_status=?, impl_hint=?, "
    "issue_number=?, issue_reactions=?, has_linked_pr=?, task_id=?, "
    "value_evidence=?, difficulty_evidence=?, urgency_evidence=?, maintainer_evidence=?, "
    "value=NULL, difficulty=NULL, urgency=NULL, maintainer_signal=NULL, "
    "status='open', last_seen_at=? "
    "WHERE project_id=? AND source_type=? AND source_ref=?",
    (title, description, canonical_status, peer_status, impl_hint,
     issue_number, issue_reactions, has_linked_pr, task_id,
     json.dumps(value_evidence_dict),
     json.dumps(difficulty_evidence_dict),
     json.dumps(urgency_evidence_dict),
     json.dumps(maintainer_evidence_dict),
     now,
     project_id, source_type, source_ref)
)
```

> **重要**：UPDATE 语句必须完整执行上述所有列，包括 `value=NULL` / `difficulty=NULL` / `urgency=NULL` / `maintainer_signal=NULL` / `status='open'`。前四列置 NULL 是触发 scoring.py 重新计算的唯一机制（scoring.py 查询条件为 `WHERE value IS NULL`）；`status` 重置为 `'open'` 是为了保证：若 scoring.py 因 JSON 解析异常跳过该行，status 不会残留旧的 `'obsolete'` 值（scoring.py 在 signal=rejected 时会将其改回 `'obsolete'`，不影响正常流程）。**不可只更新描述字段而省略这些列**，否则 scoring.py 不会重算，旧评分将持续展示，且 status 可能与实际信号不一致。

**标记完成（同时更新增量调度基准快照）：**

```sql
UPDATE tasks    SET status = 'done',   finished_at = '<now>' WHERE id = <task_id>;
UPDATE projects
SET status           = 'active',
    prev_stars       = COALESCE(stars,       prev_stars),
    prev_open_issues = COALESCE(open_issues, prev_open_issues)
WHERE id = '<project_id>' AND status = 'analyzing';
```

## 评分标准

**value（贡献价值）：由 scoring.py 根据 `value_evidence` 自动计算，规则如下（仅供参考，不要直接写入 `value` 列）：**
- `high`：原版已实现 + reactions >= 5；或原版已实现（reactions < 5）且 welcoming 信号上调
- `medium`：原版已实现（reactions < 5）；或无原版实现但有 welcoming 信号
- `low`：无原版实现参照，且无 welcoming 信号

**difficulty（实现难度）：由 scoring.py 根据 `difficulty_evidence` 自动计算，规则如下：**
- `high`：无原版实现参照（`canonical_impl_url` 为空）；或原版实现行数 > 500；或 medium 基础上触发 HARD_KEYWORDS 升级
- `medium`：原版实现行数 200~500；或行数未知（填 0）；或 low 基础上触发 HARD_KEYWORDS 升级
- `low`：有原版实现参照且行数 < 200，且无 HARD_KEYWORDS
- HARD_KEYWORDS（`why_hard` 含以下词）触发**逐级上调**（low→medium，medium→high，high 不变）：核心数据结构/并发设计/语言特性限制/core data structure/concurrency/language limitation

**urgency（紧迫度）：由 scoring.py 根据 `urgency_evidence` 自动计算，规则如下：**
- `high`：有 CVE 编号；或 `source_type=security`；或 `source_type=performance` 且有生产信号；或有生产信号且无 workaround
- `medium`：有生产信号但有 workaround；或无生产信号但有 workaround
- `low`：无生产信号且无 workaround（纯增强型功能）

**maintainer_signal（由 scoring.py 自动计算，取值：`welcoming` / `rejected` / `unknown`）：**
- `welcoming`：有 merged 的相关 PR；或 maintainer 回复含欢迎贡献语义；或 issue 有 help-wanted/good-first-issue 标签
- `rejected`：有 closed-without-merge 且含明确拒绝语义的 PR；或 maintainer 回复含拒绝语义（优先级高于 welcoming）
- `unknown`：无任何信号

## 注意事项

- 所有 `<now>` 时间戳统一使用 UTC ISO 8601 格式，如 `2026-04-17T10:30:00+00:00`（含时区偏移）
- **SQL 执行方式**：优先使用 Python `sqlite3` 模块的**参数化查询**（`conn.execute("... WHERE id=?", (task_id,))`），完全避免字符串拼接和引号转义问题。只有在无法使用参数化查询时（如动态列名），才手动拼接 SQL 字符串并做转义。
- **SQL 单引号转义**（仅在必须字符串拼接时）：将所有嵌入 SQL 的文本值中的单引号 `'` 替换为 `''`（两个单引号），防止语法错误。**高风险字段**（来自 GitHub 数据，极可能含单引号）：`title`（issue 标题如 `"Support 'async' mode"`）、`description`、`canonical_gap`、`peer_comparison`、`impl_hint`、`canonical_status`、`peer_status`、`filter_reason`、`source_structure`（`notes` 字段常含英文缩写如 `it's`、`don't`），以及所有 evidence JSON 字符串值（如 `why_hard` 中的 `"won't fix"`）。示例：`won't fix` → `won''t fix`；`it's broken` → `it''s broken`
- **`conn` 对象生命周期**：`conn = sqlite3.connect(DB_PATH)` **必须在所有任务的 for 循环外创建一次**，不要在每个任务内部创建新连接；所有任务处理完毕后，在循环外调用 `conn.close()` 显式关闭连接。每个任务内只调用 `conn.commit()`，不调用 `conn.close()`
- 每个项目分析完（Step 7 全部 SQL 执行完后）立即调用 `conn.commit()` 持久化，不要等所有项目分析完再批量写——Python `sqlite3` 的 `execute()` 不会自动持久化，未 commit 的写入在 `conn.close()` 时会被回滚丢失
- **GitHub API 调用频率**：每次 GitHub REST API 调用后等待 1 秒，避免触发 secondary rate limit（GitHub 对短时间内的并发请求有额外限制，超出后返回 403）；Search API（`/search/issues`）调用后等待 2 秒（Search API 限额更严格：30 req/min）
- **API 错误处理原则**：
  - Step 6/6.5 中单个 issue 或 PR 的 API 调用失败（超时/404）→ 跳过该 issue/PR，继续分析其他 issue，**不中止整个任务**
  - Step 2 的核心 API（项目主页、issues 列表、目录结构）失败，或 Step 3 的 `canonical_url` 抓取发生**网络超时 / 5xx 服务器错误**（临时故障）→ 中止当前任务，执行以下 SQL 后继续下一个任务（根据 `task_type` 决定项目回滚状态）：
  ```sql
  UPDATE tasks SET status = 'skipped' WHERE id = <task_id>;
  ```
  - 若 `task_type` 为 `triggered` 或 `incremental`（项目原本是 active）：
    ```sql
    UPDATE projects SET status = 'active'       WHERE id = '<project_id>' AND status = 'analyzing';
    ```
  - 若 `task_type` 为 `bulk_first` 或 `bulk_followup`：
    ```sql
    UPDATE projects SET status = 'bulk_pending' WHERE id = '<project_id>' AND status = 'analyzing';
    ```
  - Step 3 的 `canonical_url` 抓取返回 **404 Not Found**（URL 失效或仓库已删除），或 WebFetch 返回内容但**无法解析有效功能列表**（如 HTML 错误页、空页）→ **不中止**，降级为无 canonical 对比：`canonical_gap` 填 `"canonical_url 无法访问 (404)"`, `peer_comparison` 填 `"—"`，继续执行 Step 4 及后续步骤（Step 5 源码分析、Step 6 Issues 分析仍正常进行）
- 机会点宁少勿滥：只输出有明确参考实现或明确 issue 支撑的机会
- 每个项目输出机会点上限：10 个
- evidence 的主观字段（gap_desc/why_hard 等）必须基于客观字段（URL/行号/引用原文）推导，不能凭空断言
