# v3 执行记录（subagent-driven development）

## 进度 ledger

# SDD progress — feat/analysis-v3 (plan: docs/superpowers/plans/2026-07-30-analysis-v3.md)
Baseline: 63 tests OK, branch feat/analysis-v3 @ b9bd439
Plan reviews: flow (1 must-fix + 6 suggestions, all merged) + code (no hard must-fix; 3 minor fixes merged b9bd439)
Minor findings parked for final review triage:
- validate.py lacks requests ImportError auto-install fallback (analyze.py has one; requirements.txt covers it, low risk)
- Task 3 Step5: verify report file exists in git before diff (git cat-file -e)
- ingest could log opp_ids for traceability (optional)
- Task 11 git add .gitignore is no-op (already committed in Task 9)
Task 1: complete (commits b9bd439..7f09791, review clean: spec ✅, quality Approved)
  Minor parked: TestRunPreservesVerified 仅单条端到端路径；方法内 import（照抄简报）
Task 2: complete (commits 7f09791..d7dbf5b, review clean: spec ✅, quality Approved)
  Minor parked: tests/test_analyze.py COLUMNS 死代码（简报原文）；open/draft 重分析路径未显式覆盖
Task 3: complete (commits d7dbf5b..34e9c0d, review clean: spec ✅, quality Approved)
  Minor parked: test_report 未断言 ✓ 标记本身（简报测试覆盖缺口）；"今日仍 open" 文案待统一
  Phase 2 提示: 灰度对比日报时应固定 DB 快照（库持续漂移，旧日期重放不可比）
Task 4: complete (commits 34e9c0d..5f7943c 含 py3.9 修复, review clean: spec ✅, quality Approved)
  Minor parked: bool 防护无用例；pending 删除无断言；audit3 不一致 WARN 无测试；--db 指错时 traceback 而非 WARN；测试 open() 未关闭
Task 5 interim: implemented (61f6ac2), fix in flight — verified 行豁免 feature_verification 检查（解决 legacy confirm→refute 冲突）
  Phase 2/3 运行提示: ① validate 正式运行只走 --today/--opp-ids 增量，绝不全表（4982 行 × 1s+API ≈ 1.5h+ 且易限流） ② 存量回扫前先全量 dry-run 评估 legacy feature_gap 影响面
Task 5 interim2: review spec ✅/Approved；Important 修复在途（非404 4xx 归入 API 错误）
  ⚠️ 已裁决: scoring 复评会捞 value=NULL 的 verified 行（Task 1 已把查询改为 IN('open','verified')），verified corrected 行不会变僵尸
Task 6: complete (commits 1adc0c7..20de688, review clean: spec ✅, quality Approved; golden 16/16 baseline 命中)
  Minor parked: makedirs 裸文件名边界；argparse exit2 与红线 exit2 撞码（fail-closed 方向安全）；exit2 红线路径无测试
Task 5: complete (commits 5f7943c..d7fed90 共3个：功能+verified豁免+4xx修复, review: spec ✅, Approved, fix re-review ✅)
  Minor parked: dry-run stats 全零展示；check5 提前 return 丢弃已累积 strip/blank；sys 未使用
Task 7: complete (commits d7fed90..3dd6845, review: spec ✅, quality Approved)
  评审 Important 裁决为误报: "project_id 是整数" 前提错误——实测 projects.id/opportunities.project_id 均为 owner/repo 字符串（如 05bit/peewee-async），repo:<project_id> 渲染后是合法 GitHub 搜索语法，不修
  Minor parked: "留待下批" 口径不一；原则7步骤2上下文指向模糊；HEADERS 未定义依赖惯例（Phase 2 prompt 调优时一并处理）
Task 8: complete (commits 3dd6845..556c96b, review: spec ✅, quality Approved)
  Minor parked: corrected SQL 不覆盖 issue_reactions 列（spec 层瑕疵；下游 scoring 只读 JSON 字段，validate.py 同惯例，Phase 2 修订）
Task 9: complete (commits 556c96b..f15bce0, review: spec ✅ v2 等价性逐行通过, quality Approved)
  Minor parked: run.sh:99 注释行号陈旧；verify 空批时同批重选至预算耗尽（有界 ≤3 批，Phase 2 可加本轮 id 排除）；pending 时间戳秒级精度
  Phase 2 提示: v3 端到端首跑建议 ANALYZE_PROMPT_VERSION=v3 VERIFY_MAX_PER_RUN=2 小预算
Task 10: complete (commits f15bce0..a1df47a, review: spec ✅, quality Approved; 函数体 IDENTICAL 复核通过)
  Minor parked: run_bulk_v2.sh:301 重试 WARN 文案 "analyze_v2" 在 v3 模式误导（既有文本，后续统一中性措辞）
Task 11: complete (commits a1df47a..4627fc7, review: spec ✅, quality Approved)
  Minor parked: pending 秒级撞名（run.sh 同款）；verify 成功+ingest 失败时同批重选烧预算（有界终止）
Task 12: complete (commits 4627fc7..d0bf7eb, review: spec ✅, quality Approved; 全量 95 tests OK)
  Minor parked: CLAUDE.md 阶段表行序 4→4.7→4.8→4.5 非单调；"无单元测试"旧表述待修正
ALL 12 TASKS COMPLETE — entering final whole-branch review
Final review: READY TO MERGE (0 Critical, 1 Important F1 可合并/Phase3前必修, 2 Minor)
  F1: validate 作用域只传已裁决 id（三处同构）; F2: PENDING=0 补初评; F3: CLAUDE.md 修正
  fix-final agent dispatched for all three
Final fixes: complete (commit 25e1410; syntax OK, IDENTICAL, 95 tests OK)
BRANCH READY FOR MERGE DECISION

---

## 终审报告

# Final whole-branch review — feat/analysis-v3 (b9bd439..d0bf7eb, 15 commits)

日期：2026-07-30
评审人：final-reviewer（跨任务整体性风险镜头）
输入：设计文档 docs/superpowers/specs/2026-07-30-analysis-v3-design.md、全分支 diff、progress.md ledger
实证核查：pipeline.db 零 diff、v2 链路文件（analyze_v2.md/analyze.md/init_db.py/filter.md）零 diff、95 tests OK、.gitignore 对 .pending_* 生效

## 1. 总体判决

**READY TO MERGE** — 无 Critical；1 个 Important（F1）建议合并后、Phase 3 存量回扫前必修；其余为 Minor/已 parked。

## 2. 五镜头结论

### A. v2 零行为变化：成立

- 默认 `ANALYZE_PROMPT_VERSION=v2`：`REFINE_PROMPT=analyze_v2.md`，sed 占位符与渲染逻辑逐行未动；`run_v3_verify` 仅在 v3 分支调用（run.sh:257、run.sh:377-379、run_bulk_v2.sh 同构）。
- scoring.py 两处改动在纯 v2 库下为 no-op：库中不存在 `verified` 行（无任何 v2 代码路径写入），`IN ('open','verified')` 等价于 `='open'`；`_writeback_status` 对 open 行返回 open，与旧的无条件写 'open' 一致。
- analyze.py ON CONFLICT 保护：v2 库无 `refuted` 行，CASE 恒走 ELSE 分支，与 main 等价。
- report.py：查询条件 `IN ('open','verified')` 在 v2 库等价；**唯一可见差异是报告模板新增"验证"列与"已验证机会点"统计行（v2 下恒为空/0）**——additive cosmetic，spec 4.1 明确批准，非灰度开关门控。
- git add 段新增行在 v2 模式下同样执行，但全部带 `2>/dev/null || true`，目录/文件不存在时为 no-op。
- v2 链路文件（analyze_v2.md、analyze.md、init_db.py、filter.md）经 `git diff b9bd439..d0bf7eb` 实证零改动。

### B. 跨任务接口闭环：无死胡同

逐状态机转换核查（draft → open → verified/refuted；→ obsolete；→ DELETED）：

| 转换 | 执行者 | 闭环确认 |
|------|--------|----------|
| draft → open / DELETE | analyze_v3 精炼 | v2 骨架沿用，占位符一致 |
| open → verified/refuted/corrected | verify LLM 直接 UPDATE + ingest 审计 | 三裁决与 `VERDICT_TO_STATUS` 映射一致；审计 3 抽查 verdict↔DB 一致性 |
| corrected → 复评 | verified + value=NULL → scoring 查询 `IN('open','verified') AND value IS NULL` 捞中，`_writeback_status` 保持 verified | 有集成测试 TestRunPreservesVerified |
| open/verified → refuted | validate.py 核账失败 | refuted 后不再被 scoring/verify/report 触及（三处查询均正枚举） |
| open/verified → obsolete | scoring signal=rejected | 既有终态语义不变 |
| verified → draft → 重走 | analyze.py ON CONFLICT（ELSE 分支） | 有测试 test_verified_row_returns_to_draft |
| refuted 终态保护 | analyze.py CASE WHEN | 有测试 test_refuted_row_survives_reanalysis |
| 僵尸行（open+value=NULL，JSON 解析失败产物） | 每轮 scoring 重试 + validate 僵尸巡检 WARN | 不静默死 |
| verify CLI 失败 | 行停留 open，下轮重选；预算递减保证循环有界终止 | run_verify_backlog.sh 失败即 break 防死循环 |

唯一闭环瑕疵见 F2（PENDING=0 分支顺序），影响为延迟一天自愈合，非死胡同。

### C. spec 覆盖：全覆盖，无 spec 外建设

对照 4.1 组件表 12 项逐一在 diff 中定位（含 .env.example、.gitignore、CLAUDE.md、golden.jsonl 16 条 + baseline_v2.json 16/16 命中快照）。第 5 章各节（5.1 黑名单+二元协议、5.2 反驳清单+merged_at 陷阱、5.3 ingest 三审计、5.4 ON CONFLICT、5.5 五校验项+僵尸巡检+schema 漂移防御、5.6 eval、5.7 灰度+防污染、5.8 回扫、5.9 git add 清单）均有对应实现。tests/ 为 plan 规定的 TDD 产物，非 spec 外建设。偏差仅 F2（PENDING=0 分支未先跑初评，与 4.2 数据流顺序及 run_v3_verify 自身前置条件注释不符）。

### D. parked Minor 分拣：见第 3 节

### E. 数据安全

- **pipeline.db 在 15 个 commit 中零 diff**（`git diff --stat` 实证为空），工作树干净。
- **存量 4982 条 open 不会被首日批量判死（有护栏）**：validate 在生产脚本中只以 `--today`/`--opp-ids` 增量作用域运行，无任何全表调用点；`--today` 命中的当日行均为 v3 精炼产物（feature_gap 必带 feature_verification），安全。全表 dry-run 评估是 ledger 已载的 Phase 3 前置动作。
- **但存在 F1 缺口**：批内漏判的 legacy feature_gap 行会被 validate check5 自动 refute（见下）。
- .pending_* 已被 .gitignore 覆盖（`git check-ignore -v` 实证），ingest 后删除；verify_log 目录 git add 不会混入临时文件。
- refuted 反向保护（误判死）依赖 eval 红线监控 + JSONL 留痕可溯源，机制完备。

## 3. 发现清单

### F1 [Important] 批内漏判的 legacy feature_gap open 行会被 validate 无验证判死

- 位置：`run.sh:120-125`（all_opp_ids 累积的是**选中** id 而非**已裁决** id）→ `stages/validate.py:181-191`（check5：open + feature_gap + 无 feature_verification → refuted）；`run_verify_backlog.sh:96-103`、`run_bulk_v2.sh` 内嵌 run_v3_verify 同构。
- 机制：verify 批次 20 条 legacy open feature_gap → LLM 漏判其中 k 条（停留 open，ingest 只 WARN）→ validate `--opp-ids` 包含全部 20 条 → 漏判的 k 条因无 feature_verification 被 check5 直接 refute——**未经任何实际核查即判死**。若漏判行是真机会（golden 中 real 样本含 3 条 feature_gap），构成红线指标意义上的误杀。1adc0c7 的 verified 豁免解决了"已裁决行被二次误杀"，但未覆盖"未裁决行"这个缺口。
- 影响面：Phase 2 小预算 + 人工抽查 + eval 红线兜底，风险可控；Phase 3 存量回扫（2156 medium 中含大量 legacy feature_gap）规模放大后必现。
- 处置建议：**可合并，Phase 3 前必修**。最小修法：ingest 之后、validate 之前，从 DB 重查已裁决集合（`SELECT id FROM opportunities WHERE id IN (csv) AND status IN ('verified','refuted')`），validate `--opp-ids` 只传已裁决 id（open 漏判行的其他核账项本就无新证据可核，下一轮 verify 裁决后再核不迟）；或给 check5 增加"仅当行在当批已被裁决"的门控。三处脚本同源，一并修。

### F2 [Minor] PENDING=0 分支 verify 先于 scoring 初评

- 位置：`run.sh:253-259`：v3 分支先调 `run_v3_verify`（其前置条件注释 run.sh:70 要求"调用前已运行过一次 scoring.py 初评"），scoring 在 run.sh:259 才跑。
- 影响：零任务日若有上轮崩溃遗留的 open+value=NULL 行，当天 verify 选不中它们（scoring 在 verify 之后才补分），延迟一天自愈合；legacy 行均有评分，实际命中概率≈0。与 spec 4.2 数据流顺序不符。
- 处置建议：合并后迭代——把该分支的 scoring.py 调用挪到 run_v3_verify 之前（一行顺序调整）。

### F3 [Minor] CLAUDE.md 自述与现实脱节

- "无单元测试"表述在 95 tests 落地后已误导（CLAUDE.md 关键设计决策节）；阶段表行序 4→4.7→4.8→4.5 非单调。
- 处置建议：零风险文档修复，建议合并前顺手一个 commit 修掉；不修也不阻塞。

### 其余

无 Critical。无其他 Important。

## 4. parked Minor 分拣表

| # | 来源 | 条目 | 判决 |
|---|------|------|------|
| 1 | 全局 | validate.py 无 requests ImportError 自装兜底 | 不修（requirements.txt 覆盖） |
| 2 | 全局 | Task 3 Step5 git cat-file 验证报告文件 | 不修（流程项，已执行） |
| 3 | 全局 | ingest 可记录 opp_ids 便于溯源 | 合并后迭代（optional） |
| 4 | 全局 | Task 11 git add .gitignore no-op | 不修（无害） |
| 5 | Task 1 | TestRunPreservesVerified 单路径；方法内 import | 不修 |
| 6 | Task 2 | test_analyze.py COLUMNS 死代码；open/draft 重分析未显式覆盖 | 死代码合并后随手清；覆盖不修 |
| 7 | Task 3 | test_report 未断言 ✓ 标记；"今日仍 open" 文案 | 合并后迭代（断言一行事） |
| 8 | Task 4 | bool 防护/pending 删除/audit3 无测试；--db 指错 traceback；open() 未关闭 | 合并后迭代（测试加固批） |
| 9 | Task 5 | dry-run stats 全零展示；check5 提前 return 丢弃 strip/blank；sys 未使用 | 均不修（refute 为终态，丢弃的 strip 无意义；其余 cosmetic） |
| 10 | Task 6 | makedirs 裸文件名边界；argparse exit2 与红线 exit2 撞码；exit2 无测试 | 不修（fail-closed 方向安全） |
| 11 | Task 7 | "留待下批"口径；原则7步骤2上下文；HEADERS 未定义 | 合并后迭代（并入 Phase 2 prompt 调优轮） |
| 12 | Task 8 | corrected SQL 模板缺 issue_reactions 列（prompt 第 58 行要求修正该字段但模板不含；下游 scoring 只读 JSON，影响为列值陈旧） | 合并后迭代（Phase 2 prompt 修订，模板加 `issue_reactions=?`） |
| 13 | Task 9+11 共振 | **verify 空批/ingest 失败时同批重选烧预算**：run.sh、run_bulk_v2.sh、run_verify_backlog.sh 三处同源（预算递减保证有界终止，非死循环） | 合并后迭代，三处一起修（本轮已试 id 排除；建议顺手把 verify 循环抽成共享 sourced 文件消除三份拷贝） |
| 14 | Task 9+11 | pending 文件名秒级精度撞名 | 不修（批间隔分钟级，碰撞实际不可能） |
| 15 | Task 9 | run.sh:99 注释行号陈旧 | 合并后随手清 |
| 16 | Task 10 | run_bulk_v2.sh:301 重试 WARN 文案 "analyze_v2" 在 v3 模式误导 | 合并后迭代（中性措辞） |
| 17 | Task 12 | CLAUDE.md 行序 + "无单元测试" | 即 F3，建议合并前顺手修 |

跨任务共振项只有 #13（预算燃烧三处同源）与 F1（三处同构的 validate 作用域问题），均已在发现清单定级。

## 5. Phase 2 首跑建议（给用户）

1. **小预算首跑**：`ANALYZE_PROMPT_VERSION=v3 VERIFY_MAX_PER_RUN=2 bash run.sh 10 2`，跑完人工逐条核对 `data/verify_log/YYYY-MM-DD.jsonl` 与 quarantine.jsonl，确认裁决理由质量后再放量。
2. **刷新 baseline 再开跑**：baseline_v2.json 快照于 2026-07-30；若首跑日晚于该日（库持续漂移），先重跑 `python3 stages/eval_compare.py --baseline` 固定对照快照，否则 compare 的"窗口内重分析剔除"会误剔大量样本。
3. **严守防污染纪律**：同一天同一 DB 只跑一个版本——v3 日不要再用 run_bulk_v2.sh 跑 v2 存量，否则对照组被 verify/validate 改动，eval 指标失真。
4. **每轮跑完即核红线**：`python3 stages/eval_compare.py --compare`；真机会保留率 <95%（exit 2）立即停止放量、回查 verify log 误杀条目并调 prompt，未达标前禁入 Phase 3。
5. **Phase 3 回扫前两件事**：先修 F1（validate 只核已裁决行，三处脚本同改），再 `python3 stages/validate.py --dry-run`（不带 --today/--opp-ids 需自行评估规模，或分批 --opp-ids）评估 legacy feature_gap 影响面，然后再启动 run_verify_backlog.sh。
