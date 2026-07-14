# TODO

## 1. 二进制 DB 并发推送 rebase 冲突（2026-07-13 实锤）

### 问题

`data/pipeline.db` 是 SQLite 二进制文件且纳入 git 追踪。存在两个写入方：

- **本地**（run.sh / run_bulk_v2.sh）：分析结果，commit+push DB
- **GitHub Action**（discover.yml，每日 UTC 17:00）：discover+schedule，commit+push DB

两边并发提交时，后推送的一方 `git pull --rebase` 会撞上二进制冲突
（`Cannot merge binary files: data/pipeline.db`），**SQLite 文件无法做内容级合并**。

2026-07-13 实战：本地分析推送与 Action cron 并发，Action 运行 A 的 push 被拒，
retry 中的 `git pull --rebase` 撞二进制冲突后卡死在 rebase 中途，后续 retry
全部失败（`unmerged files` / `not on a branch`），运行以 failure 结束。
（当天靠 GitHub cron 补发的第二次运行 B 兜底，数据零丢失——但属于侥幸。）

### 当前 retry 逻辑的两个缺陷

1. rebase 冲突后没有恢复路径，仓库被留在 rebase 中途状态（本地若撞上，下次 run.sh 直接起不来）。
2. `git rebase --continue` 在非交互环境会卡编辑器，需要 `GIT_EDITOR=true`。

### 修复方案：非对称让位（按数据可重建性决定优先级）

| 写入方 | 冲突策略 | 理由 |
|---|---|---|
| 本地（run.sh / run_bulk_v2.sh / run_bulk.sh） | **本地赢**：`git checkout --theirs -- data/pipeline.db`（rebase 中 theirs=本地提交）→ `git add` → `GIT_EDITOR=true git rebase --continue` → push | 分析结果消耗 LLM token，不可重跑 |
| Action（discover.yml） | **Action 让位**：`git rebase --abort` → `git reset --hard origin/main` → WARN 退出（exit 0） | discover 幂等，下次 cron 自动重建 |

### 待办

- [ ] discover.yml：push retry 循环加二进制冲突检测与让位逻辑
- [ ] run.sh / run_bulk_v2.sh / run_bulk.sh：push retry 循环加冲突恢复（checkout --theirs + GIT_EDITOR=true rebase --continue）
- [ ] （可选）本地改为每批 commit+push，把冲突窗口从"整轮数小时"缩到"单批 ~10 分钟"
- [ ] （长期）评估 DB 移出 git：Release artifact / 独立数据分支 force-push / SQL 级增量同步

### 验证方式

构造并发场景：本地 run.sh 运行期间手动 dispatch Action，观察后推送方是否按策略自动恢复。
