# Stage 4 分析质量升级（v3）设计文档

日期：2026-07-30
状态：已批准（用户逐节确认）
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
3. feature_gap 引入二元判定协议：无"搜索未命中证据"的缺口不允许入库
4. 建立种子评测集，量化 v3 相对 v2 的精度变化
5. 支持存量回扫（现有 225 条 high + 2156 条 medium）

### 成功标准

- **假机会清除率**：评测集 fake 样本被 refuted 的比例（目标越高越好，Phase 2 定基线）
- **真机会保留率**（红线）：评测集 real 样本未被 refuted 的比例 ≥ 95%
- v2 链路在灰度期间行为零变化（对照组不被污染）

### 非目标（YAGNI）

- 不浅克隆仓库 grep（本期纯 GitHub API 定向核查）
- 不动 `stages/analyze.py` 的 draft 生成逻辑（二元判定加在精炼层，不改抓取层）
- 不做 merged PR 反馈闭环（用户已明确降级）
- 不引入新 DB 表/列（DDL 仅备忘，见附录 A）
- 不改 `prompts/filter.md` / discover / schedule（与精度问题无关）
- 不改 `prompts/analyze.md`（run_bulk.sh 旧链路保留）、`prompts/analyze_v2.md`（灰度对照）

## 3. 已确认的决策记录

| 决策点 | 结论 |
|------|------|
| 新 prompt 落位 | 新文件 `prompts/analyze_v3.md` + `prompts/verify_v3.md`；`analyze_v2.md` 原样保留；环境变量灰度切换 |
| 验证范围 | 增量（新机会点）+ 存量回扫（独立入口脚本） |
| 评测集 | 本期建种子评测集（15~20 条）+ 对比脚本 |
| 核查手段 | GitHub API 定向核查（目录树 + code search），不浅克隆 |
| 架构方案 | 方案 B：独立 verify 阶段（find → verify 双会话），非一体化自验 |
| SQLite | 不动 pipeline.db，不加列不加表；验证理由写 JSONL 日志；DDL 仅备忘 |

## 4. 架构

### 4.1 组件清单

| 组件 | 类型 | 职责 |
|------|------|------|
| `prompts/analyze_v3.md` | 新 prompt | 升级版精炼（draft→open），证据要求收紧，feature_gap 强制"搜索未命中证据" |
| `prompts/verify_v3.md` | 新 prompt | 对抗验证，独立 CLI 会话，只反驳不生成 |
| `stages/validate.py` | 新 Python | 机器校验证据真伪（API 核验 PR/issue/URL/label） |
| `stages/eval_compare.py` + `data/eval/golden.jsonl` | 新 | 种子评测集 + v2/v3 精度对比 |
| `run_verify_backlog.sh` | 新脚本 | 存量回扫入口，复用 verify_v3.md + validate.py |
| `run.sh` / `run_bulk_v2.sh` | 改 | `ANALYZE_PROMPT_VERSION` 开关（默认 v2），v3 时插入 verify/validate/复评三步 |
| `stages/scoring.py` | 小改 | 主查询 `status='open'` → `status IN ('open','verified')` |
| `stages/report.py` | 小改 | 统计排除 refuted，机会点区分 verified/unverified |
| `prompts/analyze.md`、`prompts/analyze_v2.md`、`stages/analyze.py`、`stages/init_db.py` | **不动** | v2 链路完整保留作灰度对照 |

### 4.2 v3 链路数据流

```
【批次循环，与 v2 相同】每批 BATCH_SIZE_PER_CLI 个任务：
  analyze.py (draft) → CLI#1 analyze_v3.md 精炼 (draft → open | DELETE)

【批次循环结束后，统一执行一次】
  scoring.py 初评 (value/difficulty/urgency/maintainer_signal)
  → verify 循环：verify_v3.md 对抗验证，按机会点分批喂 CLI#2
    (open → verified | refuted | verified+证据修正)
  → validate.py 机器校验 (verified/open → refuted | 剥离伪证据)
  → scoring.py 复评 (只算 value=NULL 的行)
  → report.py
```

设计要点：verify 不挂在任务批次循环内，而是在其后独立成循环——选取单位是**机会点**而非任务，与存量回扫完全同构（见 5.2/5.6，两者共用同一段 verify 循环逻辑，仅调用入口不同）。scoring.py 是纯 Python 秒级完成，初评/复评各跑一次成本可忽略。

### 4.3 状态机（零 DDL）

`opportunities.status` 当前为 `TEXT DEFAULT 'open'`，**无 CHECK 约束**，可直接新增枚举值：

```
draft → open ──→ verified ──→ (再次分析时) 回到 open 重走流程
  │       │
  │       └──→ refuted (terminal，报告排除)
  └──→ DELETED (精炼阶段直接删除)
```

- `open`：未验证（含 value=low 不值得花 token 验证的）
- `verified`：通过对抗验证；若验证中修正过证据，同时置 `value=NULL` 触发复评
- `refuted`：被验证或机器校验证伪，terminal

### 4.4 验证理由的存储（不动 DB 的关键设计）

verify/validate 的判定理由**不进 DB**，写入 append-only 日志 `data/verify_log/YYYY-MM-DD.jsonl`（git 追踪）。每行：

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

可审计、可回放、可调试误杀；pipeline.db 二进制完全不变。

### 4.5 成本纪律

- verify 只处理 `value IN ('high','medium')`；low 只做 validate.py 机器校验（几乎免费）
- CLI#2 复用现有批次重试机制（60s/180s 退避）
- verify 失败则机会点停留 `open`，下次运行自然续上，幂等

## 5. 详细设计

### 5.1 `prompts/analyze_v3.md`（相对 v2 的增量改动）

骨架与 v2 完全一致（输入 SQL、判断原则、输出操作、注意事项均保留），四处加强：

**① 假阳性黑名单（来自历史误报教训）**
新增一节，明确**不得**产出为 feature_gap 的情形：

- dotfiles / 配置文件差异（`.eslintrc`、`.editorconfig`、CI workflow）
- meta 文件差异（`LICENSE`、`CHANGELOG`、`CONTRIBUTING`、issue 模板）
- monorepo 子模块的 README/文档结构差异
- `docs/`、`examples/`、`scripts/` 目录的组织方式差异

**② feature_gap 二元判定协议（核心改动）**
每个 feature_gap 候选写库**之前**必须完成定向核查，并在 `value_evidence` 中填核查证据：

```json
"feature_verification": {
  "searched_terms": ["circuit-breaker", "circuitbreaker", "CircuitBreaker"],
  "search_scope": "repo 目录树 + GitHub code search API",
  "result": "no-hit",
  "checked_at": "2026-07-30"
}
```

- `searched_terms` ≥ 2 个英文关键词（含命名变体：连字符/驼峰/下划线）
- 核查手段：先用 analyze.py 已抓的目录树匹配，再用 `GET /search/code` 定向搜（限额约 10 req/min，强制间隔 6s；403/限额时降级为仅目录树，并在 `search_scope` 注明降级）
- **无法完成任何核查的 feature_gap 直接丢弃**（没有"未命中证据"的缺口不允许入库）
- `result` 为 `hit:<file>` 时说明功能已存在，丢弃该候选

**③ issue 类机会点的存续检查**
精炼时对每条 issue 类 draft 复核 issue 当前状态（仍 open？被标 not planned？已有 linked PR？）——v2 依赖 analyze.py 抓取时的快照，v3 要求精炼时重新确认。

**④ 证据字段向后兼容**
`feature_verification` 嵌在 `value_evidence` 内；scoring.py 只读它认识的 key，不受影响。

### 5.2 `prompts/verify_v3.md`（全新，对抗性验证）

**人设与纪律**：怀疑论者。默认每条机会点都是假的，只有找不到反驳证据时才放行。看不到分析者的推理过程，只相信自己核查到的证据。

**输入**：verify 的选取单位是机会点，不依赖 TASK_ID_LIST。由调用方（run.sh 或 run_verify_backlog.sh）渲染 OPP_ID_LIST：

```sql
-- 调用方先执行此查询选出本批机会点 ID：
SELECT o.id
FROM opportunities o
JOIN projects p ON p.id = o.project_id
WHERE o.status = 'open' AND o.value IN ('high','medium')
ORDER BY CASE o.value WHEN 'high' THEN 0 ELSE 1 END, p.stars DESC
LIMIT <VERIFY_BATCH_SIZE>;   -- run.sh 渲染

-- prompt 内再按 ID 列表取全量字段：
SELECT o.*, p.url, p.language, p.stars, m.canonical_url
FROM opportunities o
JOIN projects p ON p.id = o.project_id
LEFT JOIN project_meta m ON m.project_id = o.project_id
WHERE o.id IN (OPP_ID_LIST);
```

增量（run.sh）与存量回扫（run_verify_backlog.sh）使用完全相同的选取逻辑，只是批量参数和预算不同；当日新增机会点与历史遗留 open 机会点自然一起被处理。

**分类型反驳清单**：

| 类型 | 反驳动作（GitHub API 定向核查） |
|------|------|
| `feature_gap` | ① 用 `feature_verification.searched_terms` + 自补同义词调 code search 复核，命中即 refuted；② `canonical_impl_url` 是否指向真实文件（404 → 价值基础不成立）；③ 搜近一年 `is:pr is:merged` 该关键词，已有 merged 实现 → refuted |
| `issue`/`performance`/`compatibility` | ① issue 现状：已关闭 → refuted；被标 `not planned`/`wontfix` → refuted；已有 linked PR → refuted；② reactions 数与 evidence 明显不符 → 修正证据 |
| `security` | ① issue 存在性；② CVE 编号格式与合理性（格式造假 → refuted）；③ 声称的 `affected_file` 是否真实存在于目录树 |

**三种裁决与写库**：

- **confirmed**（反驳失败）→ `status='verified'`，写 verify log
- **refuted**（找到反驳证据）→ `status='refuted'`，写 verify log（含反驳理由和证据 URL）
- **corrected**（机会点成立但证据有误）→ 修正 evidence JSON + `value=NULL`（触发复评）+ `status='verified'`，写 log

**硬性纪律**（沿用 v2 的成熟约束）：

- 只动本批次的行；参数化查询；每项目 commit 一次；时间戳 UTC ISO 8601
- 不确定时**宁可标 verified 留给人工**
- verify 阶段**不允许 DELETE 行**，只能改状态（防止对抗 prompt 误杀数据）

### 5.3 `stages/validate.py`（纯 Python，确定性校验）

对 `status IN ('open','verified')` 的机会点逐条用 GitHub API 核账：

| 校验项 | 规则 | 失败处理 |
|------|------|------|
| `source_ref` issue URL | GET issue：404 或 state=closed | → `refuted` |
| `maintainer_evidence.similar_prs[].number` | GET pull：不存在或 merged 状态与记录矛盾 | 剥离该条目（不 refute 整条） |
| `maintainer_evidence.welcome_labels` | 与 issue 实际 labels 对比，phantom label | 剥离 |
| `value_evidence.canonical_impl_url` | 解析 `/blob/` URL，GET contents：404 或指向仓库首页 | 置空该字段（触发 difficulty/value 重算） |
| `feature_verification`（仅 feature_gap） | 缺失、或 `searched_terms` 为空、或 `checked_at` 缺失 | → `refuted` |

规则：

- 任何**修改**（剥离/置空）→ `value=NULL` 触发复评；**核账失败** → `status='refuted'`
- 全部动作写 verify log；API 限流/超时 → 跳过该条留待下次，绝不因网络问题误杀
- 复用 analyze.py 的 retry session 模式（urllib3 Retry，429/5xx 退避）；每 50 条 commit 一次
- 幂等：重复运行对已通过校验的行不产生新动作（校验结果确定性）

**与 scoring.py 的顺序依赖**：validate 在 verify 之后、复评之前跑；scoring.py 查询条件改为 `status IN ('open','verified')`，refuted 天然不再参与评分和报告。

### 5.4 种子评测集与对比脚本

**`data/eval/golden.jsonl`**（git 追踪，人工维护），每行：

```json
{"project": "owner/repo", "source_type": "feature_gap", "source_ref": "canonical:Java/xxx", "label": "fake", "notes": "dotfiles 差异误报", "labeled_at": "2026-07-30"}
```

- 种子 15~20 条：fake 样本取自历史误报模式（dotfiles/meta 文件/monorepo 文档差异类假缺口），real 样本取自有明显 canonical 实现 + 高 reactions 的机会点
- 通过 `(project, source_type, source_ref)` 三元组关联 `opportunities` 表，不引入新表

**`stages/eval_compare.py`**：

```bash
python stages/eval_compare.py --baseline   # 开 v3 前快照当前状态 → data/eval/baseline_v2.json
python stages/eval_compare.py --compare    # v3 跑完后对比，输出指标
```

- `--baseline`：记录 golden 命中行在 v2 链路下的状态（status + 评分），作为对照
- `--compare`：输出——**假机会清除率**（fake 样本被 refuted 比例）、**真机会保留率**（real 样本未被 refuted 比例，红线 ≥95%）、逐条 diff 清单供人工复核

### 5.5 灰度机制

- 开关：环境变量 `ANALYZE_PROMPT_VERSION`（默认 `v2`），写在 `.env`，run.sh / run_bulk_v2.sh 读取
- `v2`：现有链路一字不动（analyze.py → analyze_v2.md → scoring → report）
- `v3`：analyze.py → analyze_v3.md → scoring 初评 → verify_v3.md → validate.py → scoring 复评 → report
- 切换成本 = 改 `.env` 一行；回滚 = 改回来即可，DB 无迁移、无不可逆向

### 5.6 存量回扫（`run_verify_backlog.sh`）

- 独立入口，共享 `data/.pipeline.lock` 互斥；用法：`bash run_verify_backlog.sh [每批机会点数，默认 20]`
- 选取规则与 run.sh 内嵌 verify 循环完全一致（见 5.2：按 value 优先、stars 降序分批渲染 OPP_ID_LIST）→ validate.py → scoring 复评
- 可重复运行直到 open 存量清零；每轮结束 git commit/push（与现有脚本风格一致）

## 6. 错误处理与边界

| 场景 | 行为 |
|------|------|
| verify CLI 失败（含 3 次重试后） | 机会点停留 `open`，下次运行自然续处理（选数据条件含 `status='open'`），幂等 |
| validate.py 遇 API 限流/超时 | 跳过该条，不标 refuted，下次再验 |
| code search 限额耗尽（verify 内） | 降级为仅目录树核查，log 注明 `degraded: true`；该条若无法反驳则按 confirmed 处理但 log 标注低置信 |
| v3 运行中途崩溃 | 沿用现有跨天任务迁移和 analyzing 重置逻辑；verify log 是 append-only，无半写状态 |
| 回扫与增量分析并发 | 共享 `.pipeline.lock` 互斥（macOS 无 flock 时打印警告，同现有行为） |

## 7. 实施分期

- **Phase 1（本期开发）**：analyze_v3.md、verify_v3.md、validate.py、run.sh/run_bulk_v2.sh 开关、scoring.py/report.py 小改、eval 工具、run_verify_backlog.sh、种子 golden.jsonl
- **Phase 2（验证调优）**：跑 baseline → 一天 v3 增量 → eval_compare 看两个指标 → 调 prompt（预期迭代 2~3 轮）
- **Phase 3（存量回扫）**：指标达标后分批回扫存量（225 high + 2156 medium）
- **Phase 4（切换默认）**：`ANALYZE_PROMPT_VERSION` 默认改 v3，v2 文件保留一个周期后归档；届时再评估是否 apply DDL 备忘

## 8. 测试策略

项目无正式测试框架，沿用现有验证风格并加强：

1. 各新脚本支持 `--dry-run`：validate.py 打印将执行的动作不写库；eval_compare.py 本身只读
2. verify_v3.md 灰度首日：小批次（`bash run.sh 10 2`）+ 人工抽查 verify log 逐条核对
3. eval_compare.py 的真机会保留率 ≥95% 作为 Phase 2 → Phase 3 的准出条件
4. v2 链路回归：灰度期间 v2 路径代码零改动（开关默认 v2），对比日报确认无行为变化

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
