# Stage 4 分析质量升级（v3）设计文档

日期：2026-07-30
状态：设计方向已批准（用户逐节确认）；已经过双子 agent 对照代码评审并修复（v2 稿）
作者：Claude + ljh

## 1. 背景与问题

流水线当前 Stage 4 为两阶段：`stages/analyze.py`（Python 抓取 + 简单规则，产出 draft）→ `prompts/analyze_v2.md`（LLM 精炼，draft → open | DELETE）→ `stages/scoring.py`（规则评分）→ `stages/report.py`。

**核心问题：分析精度被"单遍生成、无人反驳"的架构锁死。** LLM 开放式生成幻觉率高，当前产出信噪比低：

- 机会点总量 5024，其中 value=high 仅 225（4.5%），value=low 2620（52%）
- 已知误报模式：dotfiles/meta 文件/monorepo 子模块文档差异被当成 feature_gap
- evidence JSON 为自由文本，LLM 写什么信什么，引用（PR 编号、URL、label）可能伪造

**关键洞察：LLM 在开放式生成上幻觉率高，但在验证/反驳上准确率高得多。** 解锁精度的方式是把架构从"单遍生成"改为"find → verify"双阶段，验证在独立上下文中进行。

## 2. 目标与成功标准

### 目标

1. 新增对抗性验证阶段（独立 CLI 会话），对 value≠low 的机会点逐条反驳
2. 新增机器证据校验（纯 Python + GitHub API），给 LLM 证据上"说谎成本"
3. feature_gap 引入二元判定协议：无"搜索未命中证据"的缺口不允许转为 open
4. 建立种子评测集，量化 v3 相对 v2 的精度变化
5. 支持存量回扫（现有 225 条 high + 2156 条 medium）

### 成功标准

- **假机会清除率**：评测集 fake 样本被 refuted 的比例（目标越高越好，Phase 2 定基线）
- **真机会保留率**（红线）：评测集 real 样本未被 refuted 的比例 ≥ 95%
- v2 链路在灰度期间行为零变化（代码零改动 + 灰度期 v2/v3 不同日同库运行，见 5.7）

### 非目标（YAGNI）

- 不浅克隆仓库 grep（本期纯 GitHub API 定向核查）
- `stages/analyze.py` 的 draft 生成逻辑不动，**仅一处保护性小改**：ON CONFLICT 子句保留 refuted 终态（见 5.4；评审发现不做此改动则 refuted 会被重分析复活）
- 不做 merged PR 反馈闭环（用户已明确降级）
- 不引入新 DB 表/列（DDL 仅备忘，见附录 A）
- 不改 `prompts/filter.md` / discover / schedule（与精度问题无关）
- 不改 `prompts/analyze.md`（run_bulk.sh 旧链路保留）、`prompts/analyze_v2.md`（灰度对照）

## 3. 已确认的决策记录

| 决策点 | 结论 |
|------|------|
| 新 prompt 落位 | 新文件 `prompts/analyze_v3.md` + `prompts/verify_v3.md`；`analyze_v2.md` 原样保留；环境变量灰度切换 |
| 验证范围 | 增量（新机会点）+ 存量回扫（独立入口脚本），共用同一条 verify 链路 |
| 评测集 | 本期建种子评测集（15~20 条）+ 对比脚本 |
| 核查手段 | GitHub API 定向核查（目录树 + code search），不浅克隆 |
| 架构方案 | 方案 B：独立 verify 阶段（find → verify 双会话），非一体化自验 |
| SQLite | 不加列不加表；验证理由经脚本校验后写 JSONL 日志；DDL 仅备忘 |
| refuted 复活问题（评审新增） | analyze.py ON CONFLICT 加保护，refuted 为真终态；verified 重分析时回 draft 重新验证（证据可能已更新） |

## 4. 架构

### 4.1 组件清单

| 组件 | 类型 | 职责 |
|------|------|------|
| `prompts/analyze_v3.md` | 新 prompt | 升级版精炼（draft→open），假阳性黑名单 + feature_gap 二元判定协议；沿用 v2 的三个 sed 占位符 |
| `prompts/verify_v3.md` | 新 prompt | 对抗验证，独立 CLI 会话，只反驳不生成；裁决写临时 JSON 文件，不直接写日志 |
| `stages/verify_ingest.py` | 新 Python | 校验 LLM 裁决 JSON → append 正式 JSONL 日志；坏条目隔离；DELETE/漏判审计 |
| `stages/validate.py` | 新 Python | 机器校验证据真伪（API 核验 PR/issue/URL/label）；僵尸行巡检 |
| `stages/eval_compare.py` + `data/eval/golden.jsonl` | 新 | 种子评测集 + v2/v3 精度对比 |
| `run_verify_backlog.sh` | 新脚本 | 存量回扫入口，复用 verify_v3.md + verify_ingest.py + validate.py |
| `run.sh` / `run_bulk_v2.sh` | 改 | `ANALYZE_PROMPT_VERSION` 开关（默认 v2）；v3 时插入 verify 循环/ingest/validate/复评；git add 段补新文件 |
| `stages/scoring.py` | 小改 | ① 主查询 `status='open'` → `IN ('open','verified')`；② 写回保护：仅 signal=rejected 时写 `status='obsolete'`，否则**保持原 status 不变**（不再无条件写 'open'） |
| `stages/report.py` | 小改 | 三处 `status='open'` 过滤（report.py:44 高价值机会表、:56 open_opps 统计、:58 new_opps_today 统计）全部改为正枚举 `IN ('open','verified')`；高价值表加 verified 标记列 |
| `stages/analyze.py` | 一处小改 | ON CONFLICT DO UPDATE 的 status 赋值：`refuted` 保持 `refuted`（终态保护），其余照旧重置 `draft` |
| `prompts/analyze.md`、`prompts/analyze_v2.md`、`stages/init_db.py`、`prompts/filter.md` | **不动** | v2 链路完整保留作灰度对照 |

### 4.2 v3 链路数据流

```
【批次循环，与 v2 相同】每批 BATCH_SIZE_PER_CLI 个任务：
  analyze.py (draft) → CLI#1 analyze_v3.md 精炼 (draft → open | DELETE)

【批次循环结束后，统一执行一次】
  scoring.py 初评 (value/difficulty/urgency/maintainer_signal)
  → verify 循环（受 VERIFY_MAX_PER_RUN 总量预算约束）：
      按机会点分批渲染 verify_v3.md → CLI#2 对抗验证，裁决写 data/verify_log/.pending_<ts>.json
      → verify_ingest.py 校验落盘 + 审计
      (open → verified | refuted | verified+证据修正)
  → validate.py 机器校验 (verified/open → refuted | 剥离伪证据)
  → scoring.py 复评 (只算 value=NULL 的行)
  → report.py
```

设计要点：

- verify 不挂在任务批次循环内，而在其后独立成循环——选取单位是**机会点**而非任务，与存量回扫完全同构（见 5.2/5.8，共用同一段 verify 循环逻辑）。
- **PENDING=0 提前退出分支（run.sh:174-198）同样插入 verify 循环/ingest/validate/复评**：verify 选取不依赖当日任务，零任务日恰恰是消化验证 backlog 的窗口；该分支的 git add 段同步补新文件。
- scoring.py 是纯 Python 秒级完成，初评/复评各跑一次成本可忽略。

### 4.3 状态机（零 DDL）

`opportunities.status` 为 `TEXT DEFAULT 'open'`，**无 CHECK 约束**（init_db.py:90 与实际库 `.schema opportunities` 均已核实），可直接新增枚举值：

```
draft → open ──→ verified ──→ (再次分析时) analyze.py 重置回 draft，重走精炼+验证
  │       │
  │       └──→ refuted (真终态：analyze.py ON CONFLICT 保护，重分析不复活)
  └──→ DELETED (精炼阶段直接删除)

open/verified ──(复评时 signal=rejected)──→ obsolete (既有终态，语义不变)
```

- `open`：未验证（含 value=low 不值得花 token 验证的）
- `verified`：通过对抗验证；若验证中修正过证据，同时置 `value=NULL` 触发复评。**复评不会把 verified 冲回 open**（scoring.py 写回保护，见 4.1）
- `refuted`：被验证或机器校验证伪；analyze.py 的 ON CONFLICT 保护使其不被重分析复活
- verified → obsolete：复评发现维护者拒绝信号时判死，语义合理；该转移由 scoring.py 执行，verify 日志无痕迹属既有行为（obsolete 本就不留日志），本期接受

### 4.4 验证理由的存储（不动 DB 的关键设计）

LLM（verify）与 validate.py 的判定理由**不进 DB**，最终落在 append-only 日志 `data/verify_log/YYYY-MM-DD.jsonl`（git 追踪）。每行：

```json
{
  "opportunity_id": 1234,
  "project_id": "owner/repo",
  "source": "verify|validate",
  "verdict": "confirmed|refuted|corrected",
  "reason": "code search 命中 pkg/breaker/circuit.go，功能已存在",
  "checks": ["code_search:circuit-breaker", "canonical_impl_url:200"],
  "corrections": [],
  "degraded": false,
  "ts": "2026-07-30T10:30:00+00:00"
}
```

**LLM 不直接写 JSONL**（手写流式 JSON 易产坏行：引号/换行断行、漏字段）。改为：

1. verify prompt 要求 LLM 把本批裁决以**单个 JSON 数组**写入临时文件 `data/verify_log/.pending_<批次时间戳>.json`（隐藏文件，不入 git）
2. CLI 退出后由 `stages/verify_ingest.py` 做 schema 校验，逐条 append 到正式 JSONL；坏条目移入 `data/verify_log/quarantine.jsonl` 并告警
3. ingest 同时做**审计**：裁决条数 vs 本批 OPP_ID_LIST 大小（漏判告警）；比对 DB 确认 OPP_ID_LIST 的行数未减少（verify 违规 DELETE 告警）

### 4.5 成本纪律

- verify 只处理 `value IN ('high','medium')`；low 只做 validate.py 机器校验（几乎免费）
- **verify 总量预算**：run.sh 增量路径每次运行 verify 上限 `VERIFY_MAX_PER_RUN`（环境变量，默认 50 条）；存量 2375 条 high+medium 由 run_verify_backlog.sh 分批消化，灰度首日不会爆量
- **code search 主动预算**：`GET /search/code` 限额约 10 req/min。每个 CLI 会话内调用上限 10 次、间隔 7s（不依赖 LLM 计时纪律，靠计数）；预算耗尽即降级为仅目录树核查并在证据中注明——把不可控的 LLM sleep 变成可控的计数。精炼层最坏情况（5 任务 × 5 个 feature_gap × 2 词 = 50 次）会被预算截断，这是有意设计
- 精炼（CLI#1）与 verify（CLI#2）串行执行但共享同一 code search 分钟级窗口，两步各自的预算独立计数
- CLI#2 复用现有批次重试机制（60s/180s 退避）；verify 失败则机会点停留 `open`，下次运行自然续上，幂等

## 5. 详细设计

### 5.1 `prompts/analyze_v3.md`（相对 v2 的增量改动）

骨架与 v2 完全一致：输入 SQL、判断原则、输出操作、注意事项均保留；**沿用 v2 的三个 sed 占位符**（`/path/to/pipeline/data/pipeline.db`、`ANALYSIS_DATE`、`TASK_ID_LIST`），保证 run.sh 渲染逻辑不变。数据流前提：draft 已由 analyze.py 落库，本 prompt 只做 draft → open（UPDATE）或 DELETE，从不 INSERT。三处加强：

**① 假阳性黑名单（来自历史误报教训）**
新增一节，明确以下情形的 draft **直接 DELETE**，不得转为 open：

- dotfiles / 配置文件差异（`.eslintrc`、`.editorconfig`、CI workflow）
- meta 文件差异（`LICENSE`、`CHANGELOG`、`CONTRIBUTING`、issue 模板）
- monorepo 子模块的 README/文档结构差异
- `docs/`、`examples/`、`scripts/` 目录的组织方式差异

**② feature_gap 二元判定协议（核心改动）**
每个 feature_gap 类型的 draft 在**转为 open 之前**必须完成定向核查；无法完成任何核查的 feature_gap draft **DELETE**（没有"未命中证据"的缺口不允许存活）。核查证据写入 `value_evidence`：

```json
"feature_verification": {
  "searched_terms": ["circuit-breaker", "circuitbreaker", "CircuitBreaker"],
  "search_scope": "repo 目录树 + GitHub code search API",
  "result": "no-hit",
  "checked_at": "2026-07-30"
}
```

- `searched_terms` ≥ 2 个英文关键词（含命名变体：连字符/驼峰/下划线）
- 核查手段：先用 analyze.py 已抓的目录树匹配，再在 code search 预算内（见 4.5：每会话 ≤10 次、间隔 7s）用 `GET /search/code` 定向搜；预算耗尽或 403 时降级为仅目录树，并在 `search_scope` 注明降级
- `result` 为 `hit:<file>` 时说明功能已存在，DELETE 该 draft
- **prompt 单独点名：精炼重写 `value_evidence` 时必须保留 `feature_verification` 及其他未涉及 key**——它是 validate.py 的 refute 触发项（见 5.5），重写丢失等于自己产出的机会点被机器校验判死

**③ 证据字段向后兼容**
`feature_verification` 嵌在 `value_evidence` 内；scoring.py 的 `score_value()` 只读 `canonical_impl_url`/`issue_reactions`/`has_prod_signal` 三个 key，新增嵌套 dict 不影响评分，也不会被 scoring 写回冲掉（scoring.py 只 UPDATE 评分列）。

（评审裁决：v2 稿的"精炼层 issue 存续复核"已删除——精炼距 analyze.py 快照仅分钟级，复核命中率趋近于零；存续检查统一由 verify 层执行，见 5.3。）

### 5.2 `prompts/verify_v3.md`（全新，对抗性验证）

**人设与纪律**：怀疑论者。默认每条机会点都是假的，只有找不到反驳证据时才放行。看不到分析者的推理过程；**机会点自述的证据（如 `feature_verification.searched_terms`）可见但不采信**——可以用作复核的线索，结论必须来自自己独立核查到的证据。

**输入**：选取单位是机会点，不依赖 TASK_ID_LIST。调用方（run.sh 或 run_verify_backlog.sh）先执行选取查询，再渲染 OPP_ID_LIST：

```sql
-- 调用方选取本批机会点 ID（含总量预算，见 4.5）：
SELECT o.id
FROM opportunities o
JOIN projects p ON p.id = o.project_id
WHERE o.status = 'open' AND o.value IN ('high','medium')
ORDER BY CASE o.value WHEN 'high' THEN 0 ELSE 1 END, p.stars DESC, o.id
LIMIT <VERIFY_BATCH_SIZE>;

-- prompt 内按 ID 列表取全量字段：
SELECT o.*, p.url, p.language, p.stars, m.canonical_url
FROM opportunities o
JOIN projects p ON p.id = o.project_id
LEFT JOIN project_meta m ON m.project_id = o.project_id
WHERE o.id IN (OPP_ID_LIST);
```

`o.id` 作为第二排序键保证跨批顺序稳定，回扫断点续跑不漏不重。增量（run.sh）与存量回扫（run_verify_backlog.sh）使用完全相同的选取逻辑；当日新增与历史遗留 open 机会点自然一起被处理。

**分类型反驳清单**：

| 类型 | 反驳动作（GitHub API 定向核查） |
|------|------|
| `feature_gap` | ① 用 `feature_verification.searched_terms` + 自补同义词，在 code search 预算内复核，命中即 refuted；② `canonical_impl_url` 是否指向真实文件（404 → 价值基础不成立 → refuted）；③ **similar_prs 先信后查**：`maintainer_evidence.similar_prs` 非空则逐条复核其中条目的真伪与 merged 状态（不重新搜索）；为空时才搜一次近一年 `is:pr is:merged` 该关键词，有 merged 实现 → refuted |
| `issue`/`performance`/`compatibility` | ① issue 现状：已关闭 → refuted；被标 `not planned`/`wontfix` → refuted；已有 linked PR → refuted；② reactions 数与 evidence 明显不符 → 修正证据；③ similar_prs 同样先信后查 |
| `security` | ① issue 存在性；② CVE 编号格式与合理性（格式造假 → refuted）；③ 声称的 `affected_file` 是否真实存在于目录树 |

**Search API merged_at 陷阱**（prompt 必须写明，否则 merged PR 会被误判为未合并）：`/search/issues` 返回的 PR 顶层 `merged_at` 恒为 null，需检查 `pull_request.merged_at`；降级 Pulls API 则直接检查顶层 `merged_at`（详见 analyze.md Step 6.5）。

**三种裁决与写库**：

- **confirmed**（反驳失败）→ `status='verified'`
- **refuted**（找到反驳证据）→ `status='refuted'`
- **corrected**（机会点成立但证据有误）→ 修正 evidence JSON + `value=NULL`（触发复评，复评由 scoring.py 全量重算四字段，无需置空其他评分列）+ `status='verified'`

每条裁决写库后**立即 commit**（verify 按机会点混批，v2 的"每项目 commit"措辞不适用），保证 DB 状态与裁决一一对应。

**裁决输出（不写日志文件，见 4.4）**：会话结束前把本批全部裁决以单个 JSON 数组写入 `data/verify_log/.pending_<批次时间戳>.json`，数组元素字段同 4.4 的日志行格式（缺 `source`，由 ingest 补 `verify`）。

**硬性纪律**（沿用 v2 的成熟约束）：只动 OPP_ID_LIST 内的行；参数化查询；时间戳 UTC ISO 8601；不确定时**宁可标 confirmed 留给人工**；**只允许 UPDATE status/evidence，禁止 DELETE 行、禁止 INSERT**（ingest 会做行数审计）。

### 5.3 `stages/verify_ingest.py`（裁决落盘与审计）

CLI#2 退出后由 run.sh / run_verify_backlog.sh 调用，输入为 `.pending_<ts>.json` 路径与 OPP_ID_LIST：

1. **schema 校验**：每条裁决必须含 `opportunity_id`（int）、`verdict`（枚举）、`reason`（非空字符串）；缺字段/类型错/JSON 整体解析失败 → 坏条目移入 `data/verify_log/quarantine.jsonl` 并打印 WARN
2. **落盘**：合法条目补 `source: "verify"` 与 `ts`，append 到 `data/verify_log/YYYY-MM-DD.jsonl`
3. **审计**：
   - 裁决条数 vs OPP_ID_LIST 大小：少于则 WARN（漏判，未裁决行停留 open 下次续处理，幂等安全）
   - `SELECT COUNT(*) FROM opportunities WHERE id IN (OPP_ID_LIST)` 行数减少 → WARN（verify 违规 DELETE）
   - 抽查裁决与 DB 状态一致性（verdict=refuted 的行 status 应为 'refuted'），不一致 WARN
4. 清理已处理的 `.pending_*.json`；审计结果全部打印并可被 run.sh 捕获

### 5.4 `stages/analyze.py` 保护性小改（refuted 终态保护）

现状：analyze.py:758-771 的 `ON CONFLICT(project_id, source_type, source_ref) DO UPDATE SET ... status='draft', value=NULL...` 无条件执行——同一项目重分析（triggered/incremental 是常态）会把 verified 和 **refuted** 都重置回 draft，证伪结论被冲掉并重复消耗 verify token。

改动（仅此一处）：ON CONFLICT 的 status/value 赋值加条件——

```sql
ON CONFLICT(project_id, source_type, source_ref) DO UPDATE SET
  ...,
  status = CASE WHEN opportunities.status = 'refuted' THEN 'refuted' ELSE 'draft' END,
  value  = CASE WHEN opportunities.status = 'refuted' THEN opportunities.value ELSE NULL END,
  ...
```

refuted 行：status/value 保持，证据字段照常刷新（无害），不再进入精炼/验证流程。verified 行：照旧回 draft 重走流程（重分析意味着新证据，重新验证语义正确）。

### 5.5 `stages/validate.py`（纯 Python，确定性校验）

对 `status IN ('open','verified')` 的机会点逐条用 GitHub API 核账：

| 校验项 | 规则 | 失败处理 |
|------|------|------|
| `source_ref` issue 引用 | **兼容两种格式**：`issue:<N>`（analyze.py 产出，3234 条存量）与完整 URL `https://github.com/<owner>/<repo>/issues/<N>`（旧 analyze.md 链路，1601 条存量）；解析后 GET issue：404 或 state=closed | → `refuted` |
| `maintainer_evidence.similar_prs[].number` | GET pull：不存在或 merged 状态与记录矛盾 | 剥离该条目（不 refute 整条） |
| `maintainer_evidence.welcome_labels` | 与 issue 实际 labels 对比，phantom label | 剥离 |
| `value_evidence.canonical_impl_url` | 解析 `/blob/` URL，GET contents：404 或指向仓库首页 | 置空该字段（触发 difficulty/value 重算） |
| `feature_verification`（仅 feature_gap） | 缺失、或 `searched_terms` 为空、或 `checked_at` 缺失 | → `refuted` |

规则：

- 任何**修改**（剥离/置空）→ `value=NULL` 触发复评；**核账失败** → `status='refuted'`
- 全部动作写 verify log（`source: "validate"`，Python 直接写 JSONL，无需 ingest）；API 限流/超时 → 跳过该条留待下次，绝不因网络问题误杀
- 复用 analyze.py 的 retry session 模式（urllib3 Retry，429/5xx 退避）；每 50 条 commit 一次
- 幂等：重复运行对已通过校验的行不产生新动作（校验结果确定性）
- **僵尸行巡检**：`status='open' AND value IS NULL AND last_seen_at 早于 N 天前`（N 默认 7）的行打印 WARN 清单——这类行是 scoring.py JSON 解析失败 SKIP 的产物，不进 verify（value 非 high/medium）、不进报告，需要人工或强制复评收拾；v3 的嵌套 evidence 加大了 JSON 写坏概率，此巡检必须有
- **不假设列清单**：实际库 opportunities 表比 init_db.py 的 SCHEMA 多一列 `updated_at`（schema 漂移）；新脚本一律显式列名 SELECT/UPDATE，禁止 `SELECT *` 后按下标访问

**与 scoring.py 的顺序依赖**：validate 在 verify 之后、复评之前跑；scoring.py 查询条件改为 `status IN ('open','verified')`，refuted 天然不再参与评分和报告。

### 5.6 种子评测集与对比脚本

**`data/eval/golden.jsonl`**（git 追踪，人工维护），每行：

```json
{"project": "owner/repo", "source_type": "feature_gap", "source_ref": "canonical:Java/hotspot-param-flow", "label": "fake", "notes": "dotfiles 差异误报", "labeled_at": "2026-07-30"}
```

- 种子 15~20 条：fake 样本取自历史误报模式（dotfiles/meta 文件/monorepo 文档差异类假缺口），real 样本取自有明显 canonical 实现 + 高 reactions 的机会点
- **关联方式**：`project` 存 `owner/repo`，JOIN `opportunities.project_id`（实测该列存 `owner/repo`，与 projects.id 一致；不要 JOIN projects.url，那是完整 URL）
- **`source_ref` 必须从库里抄精确值**：实测三种格式 `issue:<N>` / 完整 issue URL / `canonical:<lang>/<name>`，SQLite 等值匹配区分大小写、无模糊匹配，手写容易对不上

**`stages/eval_compare.py`**：

```bash
python stages/eval_compare.py --baseline   # 开 v3 前快照当前状态 → data/eval/baseline_v2.json
python stages/eval_compare.py --compare    # v3 跑完后对比，输出指标
```

- `--baseline`：记录 golden 命中行在 v2 链路下的状态（status + 评分 + last_seen_at），作为对照
- `--compare`：输出——**假机会清除率**（fake 样本被 refuted 比例）、**真机会保留率**（real 样本未被 refuted 比例，红线 ≥95%）、逐条 diff 清单供人工复核
- **重分析噪声处理**：baseline→compare 窗口内 `last_seen_at` 发生变化的行（被重分析刷新过）从指标计算中剔除，单独列入"需人工复核"清单——重分析会重置状态（见 5.4），其差异不能归因于 verify

### 5.7 灰度机制

- 开关：环境变量 `ANALYZE_PROMPT_VERSION`（默认 `v2`），写在 `.env`，run.sh / run_bulk_v2.sh 读取；run.sh 按开关选择渲染 analyze_v2.md 或 analyze_v3.md（占位符一致，sed 逻辑不变）
- `v2`：现有链路一字不动（analyze.py → analyze_v2.md → scoring → report）
- `v3`：analyze.py → analyze_v3.md → scoring 初评 → verify 循环 + ingest → validate.py → scoring 复评 → report（含 PENDING=0 分支，见 4.2）
- **对照组防污染**：v3 的 verify/validate 与 v2 共用同一张 opportunities 表。灰度期（Phase 2）**同一天同一 DB 只允许跑一个版本**——跑 v3 的日子不用 run_bulk_v2.sh 跑 v2，反之亦然；否则 v2 产出的 open 会被 v3 的 verify 改动，对照失真
- 切换成本 = 改 `.env` 一行；回滚 = 改回来即可，DB 无迁移、无不可逆向

### 5.8 存量回扫（`run_verify_backlog.sh`）

- 独立入口，共享 `data/.pipeline.lock` 互斥（macOS 无 flock 时打印警告，同现有行为；run.sh 的锁提示文案同步加入本脚本名）；用法：`bash run_verify_backlog.sh [每批机会点数，默认 20] [本次运行总预算，默认 100]`
- 选取规则与 run.sh 内嵌 verify 循环完全一致（见 5.2）→ ingest → validate.py → scoring 复评
- 可重复运行直到 open 存量清零；每轮结束 git add pipeline.db + data/verify_log/ 并 commit/push（与现有脚本风格一致）

### 5.9 git 追踪清单

以下新文件**均不命中 .gitignore**（已用 `git check-ignore` 实测），无需 force-add，但必须补进各脚本的 git add 段：

| 脚本 | 需新增 add 的路径 |
|------|------|
| run.sh 主路径（现 run.sh:304-310）与 PENDING=0 分支（现 run.sh:180-182） | `data/verify_log/`、`prompts/analyze_v3.md`、`prompts/verify_v3.md`、`stages/validate.py`、`stages/verify_ingest.py`、`stages/eval_compare.py`、`run_verify_backlog.sh` |
| run_bulk_v2.sh（现 run_bulk_v2.sh:254-261） | 同上 |
| run_verify_backlog.sh（新脚本自身） | `data/pipeline.db`、`data/verify_log/` |

`data/eval/golden.jsonl` 与 `data/eval/baseline_v2.json` 由人工/工具提交，不进 run.sh 自动 add 段。`data/verify_log/.pending_*.json` 为隐藏临时文件，ingest 后删除，不入 git。

## 6. 错误处理与边界

| 场景 | 行为 |
|------|------|
| verify CLI 失败（含 3 次重试后） | 机会点停留 `open`，下次运行自然续处理（选数据条件含 `status='open'`），幂等；`.pending_*.json` 可能不存在或残缺，ingest 按残缺处理并 WARN |
| ingest 发现坏条目 | 移入 quarantine.jsonl + WARN，不影响合法条目落盘 |
| ingest 审计发现漏判/违规 DELETE/状态不一致 | WARN 并打印明细；漏判行停留 open 幂等续处理；DELETE 与不一致需人工排查 verify prompt 纪律 |
| validate.py 遇 API 限流/超时 | 跳过该条，不标 refuted，下次再验 |
| code search 预算耗尽或 403 | 降级为仅目录树核查，证据注明降级；该条若无法反驳则按 confirmed 处理但日志 `degraded: true` 标注低置信 |
| v3 运行中途崩溃 | 沿用现有跨天任务迁移和 analyzing 重置逻辑；正式 JSONL 只由 ingest append，无半写状态（`.pending_*` 残缺不影响正式日志） |
| 回扫与增量分析并发 | 共享 `.pipeline.lock` 互斥（macOS 无 flock 时打印警告，同现有行为） |

## 7. 实施分期

- **Phase 1（本期开发）**：analyze_v3.md、verify_v3.md、verify_ingest.py、validate.py、analyze.py 保护性小改、run.sh/run_bulk_v2.sh 开关与 git add 段、scoring.py 两处改动、report.py 三处改动、eval 工具、run_verify_backlog.sh、种子 golden.jsonl
- **Phase 2（验证调优）**：跑 baseline → 一天 v3 增量（遵守 5.7 防污染约束）→ eval_compare 看两个指标 → 调 prompt（预期迭代 2~3 轮）
- **Phase 3（存量回扫）**：指标达标后分批回扫存量（225 high + 2156 medium）
- **Phase 4（切换默认）**：`ANALYZE_PROMPT_VERSION` 默认改 v3，v2 文件保留一个周期后归档；届时再评估是否 apply DDL 备忘

## 8. 测试策略

项目无正式测试框架，沿用现有验证风格并加强：

1. 各新脚本支持 `--dry-run`：validate.py 打印将执行的动作不写库；verify_ingest.py 打印校验/审计结果不落盘；eval_compare.py 本身只读
2. verify_v3.md 灰度首日：小批次（`bash run.sh 10 2` + 低 VERIFY_MAX_PER_RUN）+ 人工抽查 verify log 逐条核对
3. eval_compare.py 的真机会保留率 ≥95% 作为 Phase 2 → Phase 3 的准出条件
4. v2 链路回归：灰度期间 v2 路径代码零改动（开关默认 v2），对比日报确认无行为变化
5. scoring.py 写回保护的回归验证：构造一行 status='verified' + value=NULL 的数据跑复评，确认复评后 status 仍为 'verified'

## 附录 A：DDL 备忘（本期不执行）

以下候选变更**仅记录**，待 Phase 4 评估 JSONL 日志是否够用后再决定是否 apply；apply 时需在 `init_db.py` 补幂等迁移：

```sql
-- 候选 1：验证结论内嵌 DB（替代/补充 JSONL 日志）
ALTER TABLE opportunities ADD COLUMN verify_evidence TEXT;  -- JSON：{verdict, reason, checks[]}
ALTER TABLE opportunities ADD COLUMN verified_at TEXT;      -- UTC ISO 8601

-- 候选 2：status 加 CHECK 约束（防止 LLM 写入非法状态值，需重建表）
-- CHECK(status IN ('draft','open','verified','refuted','obsolete'))
```

不 apply 的代价：验证理由只在 JSONL 日志里，DB 查询无法直接 join；验证时间戳只能看日志。本期可接受。

## 附录 B：评审发现的既有事实（备查）

- 实际库 opportunities 表比 init_db.py SCHEMA 多一列 `updated_at TEXT`（schema 漂移）；新脚本不得依赖 init_db.py 的列清单假设
- source_ref 存量三种格式实测分布：`issue:<N>` 3234 条、完整 URL 1601 条、`canonical:<lang>/<name>` 189 条
- `projects.id` 存 `owner/repo`，`projects.url` 存完整 URL
- run.sh:44 锁提示文案目前只写 "run.sh 或 run_bulk.sh"，接入 run_verify_backlog.sh 后同步更新（cosmetic）

