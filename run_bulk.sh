#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$PIPELINE_DIR/data/pipeline.db"
PROMPTS="$PIPELINE_DIR/prompts"
STAGES="$PIPELINE_DIR/stages"
BATCH_SIZE=${1:-5}

# 加载 .env（若存在），否则使用默认值
if [ -f "$PIPELINE_DIR/.env" ]; then
  # shellcheck disable=SC1091
  set -a; source "$PIPELINE_DIR/.env"; set +a
fi
CLI_TOOL="${CLI_TOOL:-claude --dangerously-skip-permissions}"
# 校验 BATCH_SIZE：必须为正整数，防止 LIMIT -1 / LIMIT 0 穿透到 SQLite 处理全量项目
if ! [[ "$BATCH_SIZE" =~ ^[0-9]+$ ]] || [ "$BATCH_SIZE" -le 0 ] || [ "$BATCH_SIZE" -gt 100 ]; then
  echo "ERROR: BATCH_SIZE 必须为 1~100 之间的正整数，当前值: '$BATCH_SIZE'"
  exit 1
fi
DATE=$(date -u +%Y-%m-%d)

echo "=== Bulk Analysis - $DATE (batch_size=$BATCH_SIZE) ==="

# 进程互斥锁：与 run.sh 共享同一个锁文件，防止两个脚本并发操作同一个 SQLite DB。
# macOS 原生不提供 flock 命令行工具；若不可用，打印警告后跳过互斥锁继续运行。
_LOCK_FILE="$PIPELINE_DIR/data/.pipeline.lock"
mkdir -p "$(dirname "$_LOCK_FILE")"
if command -v flock >/dev/null 2>&1; then
  exec 9>"$_LOCK_FILE"
  if ! flock -n 9; then
    echo "ERROR: 另一个 pipeline 实例（run.sh 或 run_bulk.sh）正在运行，本次退出。"
    echo "       若确认无其他实例在运行，请删除锁文件：rm $_LOCK_FILE"
    exit 1
  fi
else
  echo "WARN: flock 命令不可用（macOS 环境），跳过进程互斥锁。请勿并发运行多个 pipeline 实例。"
fi

if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "WARN: GITHUB_TOKEN 未设置，GitHub API 限额仅 60 req/hour，analyze 阶段可能因限流失败。"
  echo "      建议：export GITHUB_TOKEN=<your_pat> 后再运行本脚本。"
fi

# 注意：若上次 push 失败导致本地有未提交修改，checkout 会丢弃这些修改——先打印 WARN 便于排查
_LOCAL_CHANGES=$(git -C "$PIPELINE_DIR/.." diff --name-only HEAD -- opensource-project-opportunities-pipeline/ 2>/dev/null || true)
if [ -n "$_LOCAL_CHANGES" ]; then
  echo "WARN: opensource-project-opportunities-pipeline/ 目录存在未提交的本地修改（可能是上次 push 失败遗留），将被丢弃并以 remote 为准："
  echo "$_LOCAL_CHANGES" | sed 's/^/  /'
fi
git -C "$PIPELINE_DIR/.." reset HEAD -- opensource-project-opportunities-pipeline/ 2>/dev/null || true
git -C "$PIPELINE_DIR/.." checkout -- opensource-project-opportunities-pipeline/ 2>/dev/null || true
# pull --rebase 失败（网络问题/冲突）时降级为警告，不中止脚本
git -C "$PIPELINE_DIR/.." pull --rebase || \
  echo "WARN: git pull --rebase 失败，以本地当前状态继续运行（可能缺少远端最新变更）。"
python3 "$STAGES/init_db.py"

# 将上次中断卡在 analyzing 状态的项目重置，使其可被重新调度
# 优先级1：有已完成任务的项目 → 曾经是 active，重置回 active（不要降级）
# 优先级2：有 triggered/incremental 类型任务（task_type 说明原本是 active）→ 重置回 active
# 优先级3：其余（bulk_first/bulk_followup）→ 首次分析未完成，重置回 bulk_pending
sqlite3 "$DB" "
UPDATE projects SET status='active'
WHERE status='analyzing'
  AND id IN (SELECT DISTINCT project_id FROM tasks WHERE status='done');
UPDATE projects SET status='active'
WHERE status='analyzing'
  AND id IN (
      SELECT DISTINCT project_id FROM tasks
      WHERE task_type IN ('triggered','incremental')
  );
UPDATE projects SET status='bulk_pending'
WHERE status='analyzing';
"

# 先执行语义过滤（将 discovered 项目转为 bulk_pending 或 filtered_skip），再统计队列
FILTER_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM project_meta WHERE filter_status='pending';")
if [ "$FILTER_COUNT" -gt 0 ]; then
  echo "[0/3] Stage 3: 语义过滤 ($FILTER_COUNT 个，每批最多 100)..."
  FILTER_PROMPT=$(sed "s|/path/to/pipeline/data/pipeline.db|$DB|g" "$PROMPTS/filter.md")
  # filter.md 每次最多处理 100 个，循环直到全部过滤完（最多 20 轮防止死循环）
  _filter_rounds=0
  while [ "$(sqlite3 "$DB" "SELECT COUNT(*) FROM project_meta WHERE filter_status='pending';")" -gt 0 ]; do
    _filter_rounds=$((_filter_rounds + 1))
    if [ "$_filter_rounds" -gt 20 ]; then
      echo "WARN: 语义过滤已执行 20 轮，仍有未过滤项目，跳出循环。"
      break
    fi
    $CLI_TOOL --print "$FILTER_PROMPT" || {
      echo "WARN: claude filter 返回非零退出码（round=$_filter_rounds），本轮跳过，剩余项目留待下次重试。"
      break
    }
  done
fi

TOTAL=$(sqlite3 "$DB" "SELECT COUNT(*) FROM projects WHERE status='bulk_pending';")
DONE=$(sqlite3 "$DB" "SELECT COUNT(*) FROM projects WHERE status IN ('active','filtered_skip');")
echo "存量进度：已完成 $DONE / 待分析 $TOTAL"

if [ "$TOTAL" -eq 0 ]; then
  echo "存量队列已清空，改用 run.sh。"
  python3 "$STAGES/scoring.py" || \
    echo "WARN: scoring.py 返回非零退出码，机会点评分可能不完整，继续生成报告并提交 DB。"
  python3 "$STAGES/report.py" --date "$DATE" || \
    echo "WARN: report.py 返回非零退出码，报告可能不完整，继续提交 DB 防止数据丢失。"
  git -C "$PIPELINE_DIR/.." add "$PIPELINE_DIR/data/pipeline.db"
  # 报告文件可能因 report.py 失败而不存在；git add 对不存在文件返回退出码 128，会触发 set -e 中止脚本。
  # 仅当文件存在时才 add，确保 DB 始终能提交，防止分析数据丢失。
  test -f "$PIPELINE_DIR/data/reports/$DATE.md" && \
    git -C "$PIPELINE_DIR/.." add "$PIPELINE_DIR/data/reports/$DATE.md" || true
  git -C "$PIPELINE_DIR/.." diff --staged --quiet || \
    git -C "$PIPELINE_DIR/.." commit \
      -m "chore: bulk queue empty, scoring/report update $DATE"
  _push_ok=0
  for _i in 1 2 3; do
    if git -C "$PIPELINE_DIR/.." push; then
      _push_ok=1; break
    fi
    echo "WARN: git push 失败（attempt $_i/3），10 秒后 pull --rebase 再试..."
    sleep 10
    git -C "$PIPELINE_DIR/.." pull --rebase || true
  done
  [ "$_push_ok" -eq 0 ] && \
    echo "ERROR: git push 连续 3 次失败，请手动推送：git -C $PIPELINE_DIR/.. pull --rebase && git push"
  exit 0
fi

# schedule.py 失败不应中断 pipeline：filter 阶段已更新项目状态，若因 schedule 异常触发 set -e 退出，
# 下次 run_bulk.sh 的 git checkout 会丢弃这些变更。降级处理同 run.sh。
python3 "$STAGES/schedule.py" --mode bulk_first --batch-size "$BATCH_SIZE" || \
  echo "WARN: schedule.py 返回非零退出码，今日可能无调度任务，继续执行后续步骤。"

PENDING=$(sqlite3 "$DB" "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status IN ('pending','running');")
if [ "$PENDING" -eq 0 ]; then
  echo "今日无待分析任务（全部被过滤），跳过分析。"
  python3 "$STAGES/scoring.py" || \
    echo "WARN: scoring.py 返回非零退出码，机会点评分可能不完整，继续生成报告并提交 DB。"
  python3 "$STAGES/report.py" --date "$DATE" || \
    echo "WARN: report.py 返回非零退出码，报告可能不完整，继续提交 DB 防止数据丢失。"
  git -C "$PIPELINE_DIR/.." add "$PIPELINE_DIR/data/pipeline.db"
  # 报告文件可能因 report.py 失败而不存在；git add 对不存在文件返回退出码 128，会触发 set -e 中止脚本。
  # 仅当文件存在时才 add，确保 DB 始终能提交，防止分析数据丢失。
  test -f "$PIPELINE_DIR/data/reports/$DATE.md" && \
    git -C "$PIPELINE_DIR/.." add "$PIPELINE_DIR/data/reports/$DATE.md" || true
  git -C "$PIPELINE_DIR/.." diff --staged --quiet || \
    git -C "$PIPELINE_DIR/.." commit \
      -m "chore: scoring/report update $DATE (no new tasks)"
  _push_ok=0
  for _i in 1 2 3; do
    if git -C "$PIPELINE_DIR/.." push; then
      _push_ok=1; break
    fi
    echo "WARN: git push 失败（attempt $_i/3），10 秒后 pull --rebase 再试..."
    sleep 10
    git -C "$PIPELINE_DIR/.." pull --rebase || true
  done
  [ "$_push_ok" -eq 0 ] && \
    echo "ERROR: git push 连续 3 次失败，请手动推送：git -C $PIPELINE_DIR/.. pull --rebase && git push"
  exit 0
fi
echo "[2/3] Stage 4: 深层分析 ($PENDING 个)..."
ANALYZE_PROMPT=$(sed \
  -e "s|/path/to/pipeline/data/pipeline.db|$DB|g" \
  -e "s|ANALYSIS_DATE|$DATE|g" \
  "$PROMPTS/analyze.md")
$CLI_TOOL --print "$ANALYZE_PROMPT" || \
  echo "WARN: claude analyze 返回非零退出码，部分任务可能未完成，继续执行评分和报告。"

echo "[3/3] 生成报告并推送..."
echo "scoring.py: 规则化评分..."
# scoring.py 失败不应中断 pipeline：analyze 阶段已将任务标记 done 并写入 DB，
# 若因 scoring 异常触发 set -e 退出，下次 run_bulk.sh 的 git checkout 会丢失这些数据。
python3 "$STAGES/scoring.py" || \
  echo "WARN: scoring.py 返回非零退出码，机会点评分可能不完整，继续生成报告并提交 DB。"

python3 "$STAGES/report.py" --date "$DATE" || \
  echo "WARN: report.py 返回非零退出码，报告可能不完整，继续提交 DB 防止数据丢失。"

REMAINING=$(sqlite3 "$DB" "SELECT COUNT(*) FROM projects WHERE status='bulk_pending';")
DONE=$(sqlite3 "$DB" "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status='done';")
SKIPPED=$(sqlite3 "$DB" "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status='skipped';")

git -C "$PIPELINE_DIR/.." add "$PIPELINE_DIR/data/pipeline.db"
# 报告文件可能因 report.py 失败而不存在；git add 对不存在文件返回退出码 128，会触发 set -e 中止脚本。
# 仅当文件存在时才 add，确保 DB 始终能提交，防止分析数据丢失。
test -f "$PIPELINE_DIR/data/reports/$DATE.md" && \
  git -C "$PIPELINE_DIR/.." add "$PIPELINE_DIR/data/reports/$DATE.md" || true
git -C "$PIPELINE_DIR/.." diff --staged --quiet || \
  git -C "$PIPELINE_DIR/.." commit \
    -m "feat: bulk analysis $DATE (done=$DONE skipped=$SKIPPED remaining=$REMAINING)"

# push 可能因 Actions 同时写入而失败（non-fast-forward）；
# 最多重试 3 次：每次先 pull --rebase 拉取远端最新再 push
_push_ok=0
for _i in 1 2 3; do
  if git -C "$PIPELINE_DIR/.." push; then
    _push_ok=1
    break
  fi
  echo "WARN: git push 失败（attempt $_i/3），10 秒后 pull --rebase 再试..."
  sleep 10
  git -C "$PIPELINE_DIR/.." pull --rebase || true
done
if [ "$_push_ok" -eq 0 ]; then
  echo "ERROR: git push 连续 3 次失败，本次分析结果已保存到本地 DB，但未推送到 remote。"
  echo "       请手动执行：git -C $PIPELINE_DIR/.. pull --rebase && git -C $PIPELINE_DIR/.. push"
fi

echo "=== 完成 === 本批: $PENDING | 剩余: $REMAINING"
