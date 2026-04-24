#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$PIPELINE_DIR/data/pipeline.db"
PROMPTS="$PIPELINE_DIR/prompts"
STAGES="$PIPELINE_DIR/stages"
DATE=$(date -u +%Y-%m-%d)

# 加载 .env（若存在），否则使用默认值
# 换 LLM 工具时只需修改 .env 中的 CLI_TOOL，无需改此脚本
# 参考 .env.example
if [ -f "$PIPELINE_DIR/.env" ]; then
  # shellcheck disable=SC1091
  set -a; source "$PIPELINE_DIR/.env"; set +a
fi
CLI_TOOL="${CLI_TOOL:-claude --dangerously-skip-permissions}"

echo "=== GitHub Opportunities Pipeline - $DATE ==="

# 进程互斥锁：防止 run.sh / run_bulk.sh 并发运行操作同一个 SQLite DB。
# flock -n：非阻塞模式，若锁已被占用立即退出（避免两个进程同时 analyze 造成 DB 锁竞争）。
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

# 检查 GITHUB_TOKEN（未设置时 GitHub API 限额仅 60 req/hour，analyze 阶段会因 rate limit 失败）
if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "WARN: GITHUB_TOKEN 未设置，GitHub API 限额仅 60 req/hour，analyze 阶段可能因限流失败。"
  echo "      建议：export GITHUB_TOKEN=<your_pat> 后再运行本脚本。"
fi

# 0. 拉取最新状态（先 pull 再 init，避免 pull 覆盖刚初始化的 DB）
# 注意：若上次 push 失败导致本地有未提交修改，checkout 会丢弃这些修改——先打印 WARN 便于排查
echo "[0/5] git pull..."
_LOCAL_CHANGES=$(git -C "$PIPELINE_DIR" diff --name-only HEAD 2>/dev/null || true)
if [ -n "$_LOCAL_CHANGES" ]; then
  echo "WARN: 存在未提交的本地修改（可能是上次 push 失败遗留），将被丢弃并以 remote 为准："
  echo "$_LOCAL_CHANGES" | sed 's/^/  /'
fi
git -C "$PIPELINE_DIR" reset HEAD 2>/dev/null || true
git -C "$PIPELINE_DIR" checkout -- . 2>/dev/null || true
# pull --rebase 失败（网络问题/冲突）时降级为警告，不中止脚本
git -C "$PIPELINE_DIR" pull --rebase || \
  echo "WARN: git pull --rebase 失败，以本地当前状态继续运行（可能缺少远端最新变更）。"

# 初始化 DB（幂等）
python3 "$STAGES/init_db.py"

# 将上次中途崩溃卡在 analyzing 状态的项目重置，使其可被重新调度
# 优先级1：有已完成任务的项目 → 曾经是 active，重置回 active
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

# 2. Stage 3: 语义过滤（先过滤，过滤后重新调度，再检查任务数）
FILTER_COUNT=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM project_meta WHERE filter_status='pending';")

if [ "$FILTER_COUNT" -gt 0 ]; then
  echo "[1/5] Stage 3: 语义过滤 ($FILTER_COUNT 个，每批最多 100)..."
  _FILTER_TMP=$(mktemp)
  sed "s|/path/to/pipeline/data/pipeline.db|$DB|g" "$PROMPTS/filter.md" > "$_FILTER_TMP"
  # filter.md 每次最多处理 100 个，循环直到全部过滤完（最多 20 轮防止死循环）
  _filter_rounds=0
  while [ "$(sqlite3 "$DB" "SELECT COUNT(*) FROM project_meta WHERE filter_status='pending';")" -gt 0 ]; do
    _filter_rounds=$((_filter_rounds + 1))
    if [ "$_filter_rounds" -gt 20 ]; then
      echo "WARN: 语义过滤已执行 20 轮，仍有未过滤项目，跳出循环。"
      break
    fi
    if echo "$CLI_TOOL" | grep -qE "cursor-agent|agent"; then
      eval "$CLI_TOOL" < "$_FILTER_TMP" || {
        echo "WARN: agent filter 返回非零退出码（round=$_filter_rounds），本轮跳过，剩余项目留待下次重试。"
        break
      }
    else
      eval "$CLI_TOOL" --print - < "$_FILTER_TMP" || {
        echo "WARN: claude filter 返回非零退出码（round=$_filter_rounds），本轮跳过，剩余项目留待下次重试。"
        break
      }
    fi
  done
  rm -f "$_FILTER_TMP"
else
  echo "[1/5] Stage 3: 无待过滤项目，跳过。"
fi

# 无论是否有过滤任务，都需要调度（触发/增量任务不依赖过滤结果）
echo "[2/5] 调度..."
python3 "$STAGES/schedule.py" --mode incremental || \
  echo "WARN: schedule.py 返回非零退出码，今日可能无调度任务，继续执行后续步骤。"

# 检查今日是否有待分析任务（过滤+调度完成后再检查）
PENDING=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status IN ('pending','running');")

if [ "$PENDING" -eq 0 ]; then
  echo "今日无待分析任务，仍执行评分和报告生成。"
  python3 "$STAGES/scoring.py" || \
    echo "WARN: scoring.py 返回非零退出码，机会点评分可能不完整，继续生成报告并提交 DB。"
  python3 "$STAGES/report.py" --date "$DATE" || \
    echo "WARN: report.py 返回非零退出码，报告可能不完整，继续提交 DB 防止数据丢失。"
  git -C "$PIPELINE_DIR" add "$PIPELINE_DIR/data/pipeline.db"
  test -f "$PIPELINE_DIR/data/reports/$DATE.md" && \
    git -C "$PIPELINE_DIR" add "$PIPELINE_DIR/data/reports/$DATE.md" || true
  git -C "$PIPELINE_DIR" diff --staged --quiet || \
    git -C "$PIPELINE_DIR" commit \
      -m "chore: scoring/report update $DATE (no new tasks)"
  _push_ok=0
  for _i in 1 2 3; do
    if git -C "$PIPELINE_DIR" push; then
      _push_ok=1; break
    fi
    echo "WARN: git push 失败（attempt $_i/3），10 秒后 pull --rebase 再试..."
    sleep 10
    git -C "$PIPELINE_DIR" pull --rebase || true
  done
  [ "$_push_ok" -eq 0 ] && \
    echo "ERROR: git push 连续 3 次失败，请手动推送：cd $PIPELINE_DIR && git pull --rebase && git push"
  exit 0
fi

echo "今日待分析任务：$PENDING 个"

# 3. Stage 4: 深层分析
echo "[3/5] Stage 4: 深层分析 ($PENDING 个任务)..."
_ANALYZE_TMP=$(mktemp)
sed \
  -e "s|/path/to/pipeline/data/pipeline.db|$DB|g" \
  -e "s|ANALYSIS_DATE|$DATE|g" \
  "$PROMPTS/analyze.md" > "$_ANALYZE_TMP"
if echo "$CLI_TOOL" | grep -qE "cursor-agent|agent"; then
  eval "$CLI_TOOL" < "$_ANALYZE_TMP" || \
    echo "WARN: agent analyze 返回非零退出码，部分任务可能未完成，继续执行评分和报告。"
else
  eval "$CLI_TOOL" --print - < "$_ANALYZE_TMP" || \
    echo "WARN: claude analyze 返回非零退出码，部分任务可能未完成，继续执行评分和报告。"
fi
rm -f "$_ANALYZE_TMP"

# 4. Stage 4.5 + Stage 5: 规则评分 + 生成报告
echo "[4/5] Stage 4.5+5: 规则评分 + 生成报告..."
echo "scoring.py: 规则化评分..."
python3 "$STAGES/scoring.py" || \
  echo "WARN: scoring.py 返回非零退出码，机会点评分可能不完整，继续生成报告并提交 DB。"

python3 "$STAGES/report.py" --date "$DATE" || \
  echo "WARN: report.py 返回非零退出码，报告可能不完整，继续提交 DB 防止数据丢失。"

# 统计实际完成数（done）和跳过数（skipped），用于 commit message
DONE=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status='done';")
SKIPPED=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status='skipped';")

# 5. 推回 repo
echo "[5/5] git push..."
git -C "$PIPELINE_DIR" add "$PIPELINE_DIR/data/pipeline.db"
test -f "$PIPELINE_DIR/data/reports/$DATE.md" && \
  git -C "$PIPELINE_DIR" add "$PIPELINE_DIR/data/reports/$DATE.md" || true

git -C "$PIPELINE_DIR" diff --staged --quiet || \
  git -C "$PIPELINE_DIR" commit \
    -m "feat: analysis report $DATE (done=$DONE skipped=$SKIPPED)"

_push_ok=0
for _i in 1 2 3; do
  if git -C "$PIPELINE_DIR" push; then
    _push_ok=1
    break
  fi
  echo "WARN: git push 失败（attempt $_i/3），10 秒后 pull --rebase 再试..."
  sleep 10
  git -C "$PIPELINE_DIR" pull --rebase || true
done
if [ "$_push_ok" -eq 0 ]; then
  echo "ERROR: git push 连续 3 次失败，本次分析结果已保存到本地 DB，但未推送到 remote。"
  echo "       请手动执行：cd $PIPELINE_DIR && git pull --rebase && git push"
fi

echo "=== 完成 ==="
echo "报告：$PIPELINE_DIR/data/reports/$DATE.md"
