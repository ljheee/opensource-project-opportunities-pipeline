#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$PIPELINE_DIR/data/pipeline.db"
PROMPTS="$PIPELINE_DIR/prompts"
STAGES="$PIPELINE_DIR/stages"
DATE=$(date -u +%Y-%m-%d)

TOTAL_PROJECTS=${1:-}
BATCH_SIZE_PER_CLI=${2:-}

if ! [[ "$TOTAL_PROJECTS" =~ ^[0-9]+$ ]] || [ "$TOTAL_PROJECTS" -le 0 ] || [ "$TOTAL_PROJECTS" -gt 1000 ]; then
  echo "ERROR: TOTAL_PROJECTS 必须为 1~1000 之间的正整数，当前值: '$TOTAL_PROJECTS'"
  echo "用法: bash run_bulk_v2.sh <总项目数> <每CLI项目数>"
  exit 1
fi
if ! [[ "$BATCH_SIZE_PER_CLI" =~ ^[0-9]+$ ]] || [ "$BATCH_SIZE_PER_CLI" -le 0 ] || [ "$BATCH_SIZE_PER_CLI" -gt 50 ]; then
  echo "ERROR: BATCH_SIZE_PER_CLI 必须为 1~50 之间的正整数，当前值: '$BATCH_SIZE_PER_CLI'"
  exit 1
fi

if [ -f "$PIPELINE_DIR/.env" ]; then
  # shellcheck disable=SC1091
  set -a; source "$PIPELINE_DIR/.env"; set +a
fi
CLI_TOOL="${CLI_TOOL:-claude --dangerously-skip-permissions}"

echo "=== Bulk Analysis v2 - $DATE (total=$TOTAL_PROJECTS, batch_size=$BATCH_SIZE_PER_CLI) ==="

# 进程互斥锁
_LOCK_FILE="$PIPELINE_DIR/data/.pipeline.lock"
mkdir -p "$(dirname "$_LOCK_FILE")"
if command -v flock >/dev/null 2>&1; then
  exec 9>"$_LOCK_FILE"
  if ! flock -n 9; then
    echo "ERROR: 另一个 pipeline 实例正在运行，本次退出。"
    exit 1
  fi
else
  echo "WARN: flock 命令不可用（macOS 环境），跳过进程互斥锁。请勿并发运行多个 pipeline 实例。"
fi

if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "WARN: GITHUB_TOKEN 未设置，GitHub API 限额仅 60 req/hour。"
fi

# 拉取最新状态
_LOCAL_CHANGES=$(git -C "$PIPELINE_DIR" diff --name-only HEAD 2>/dev/null || true)
if [ -n "$_LOCAL_CHANGES" ]; then
  echo "WARN: 存在未提交的本地修改，run_bulk_v2.sh 即将用 'git checkout -- .' 丢弃它们："
  echo "$_LOCAL_CHANGES" | sed 's/^/  /'
  echo "      若这些修改是你要保留的代码（如 stages/analyze.py、stages/init_db.py），"
  echo "      请先提交后再运行本脚本，否则修改会丢失。"
fi
git -C "$PIPELINE_DIR" reset HEAD 2>/dev/null || true
git -C "$PIPELINE_DIR" checkout -- . 2>/dev/null || true
git -C "$PIPELINE_DIR" pull --rebase || \
  echo "WARN: git pull --rebase 失败，以本地当前状态继续运行。"

python3 "$STAGES/init_db.py"

# 把跨天遗留的 bulk 任务（pending/running/analyzed）归到当天，统一交给主循环处理。
# 必须在 reset 块之前执行：否则跨天 analyzed 任务（task_date 仍是昨天）无法被
# reset 块的 "task_date='今天' AND status='analyzed'" 识别，项目会被误降级为 bulk_pending。
# 注意去重：同一 (project_id, task_type) 可能存在多条跨天遗留任务，直接 UPDATE 会撞
# UNIQUE(project_id, task_date, task_type)。处理顺序：①同组只留最新一条，其余标
# skipped；②与今天已有任务冲突的标 skipped；③迁移剩余。
sqlite3 "$DB" "
  UPDATE tasks
  SET status='skipped', finished_at=strftime('%Y-%m-%dT%H:%M:%S+00:00','now')
  WHERE task_type IN ('bulk_first','bulk_followup')
    AND status IN ('pending','running','analyzed')
    AND task_date < '$DATE'
    AND id NOT IN (
      SELECT MAX(id) FROM tasks
      WHERE task_type IN ('bulk_first','bulk_followup')
        AND status IN ('pending','running','analyzed') AND task_date < '$DATE'
      GROUP BY project_id, task_type
    );

  UPDATE tasks
  SET status='skipped', finished_at=strftime('%Y-%m-%dT%H:%M:%S+00:00','now')
  WHERE task_type IN ('bulk_first','bulk_followup')
    AND status IN ('pending','running','analyzed')
    AND task_date < '$DATE'
    AND EXISTS (
      SELECT 1 FROM tasks t2
      WHERE t2.project_id = tasks.project_id
        AND t2.task_type = tasks.task_type
        AND t2.task_date = '$DATE'
    );

  UPDATE tasks
  SET task_date='$DATE'
  WHERE task_type IN ('bulk_first','bulk_followup')
    AND status IN ('pending','running','analyzed')
    AND task_date < '$DATE';
"

# 重置上次中断卡在 analyzing 状态的项目。
# v2 特殊处理：若项目对应任务为 'analyzed'（等待 CLI 判断），保持 analyzing 状态，
# 这样本次循环可以继续把它们交给 CLI。
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
WHERE status='analyzing'
  AND id NOT IN (
      SELECT DISTINCT project_id FROM tasks WHERE task_date='$DATE' AND status='analyzed'
  );
"

# Stage 3: 语义过滤
FILTER_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM project_meta WHERE filter_status='pending';")
if [ "$FILTER_COUNT" -gt 0 ]; then
  echo "[Filter] 语义过滤 ($FILTER_COUNT 个，每批最多 100)..."
  _FILTER_TMP=$(mktemp)
  sed "s|/path/to/pipeline/data/pipeline.db|$DB|g" "$PROMPTS/filter.md" > "$_FILTER_TMP"
  _filter_rounds=0
  while [ "$(sqlite3 "$DB" "SELECT COUNT(*) FROM project_meta WHERE filter_status='pending';")" -gt 0 ]; do
    _filter_rounds=$((_filter_rounds + 1))
    if [ "$_filter_rounds" -gt 20 ]; then
      echo "WARN: 语义过滤已执行 20 轮，跳出循环。"
      break
    fi
    if echo "$CLI_TOOL" | grep -qE "cursor-agent|agent"; then
      eval "$CLI_TOOL" < "$_FILTER_TMP" || {
        echo "WARN: agent filter 返回非零退出码（round=${_filter_rounds}），本轮跳过。"
        break
      }
    else
      eval "$CLI_TOOL" --print - < "$_FILTER_TMP" || {
        echo "WARN: claude filter 返回非零退出码（round=${_filter_rounds}），本轮跳过。"
        break
      }
    fi
  done
  rm -f "$_FILTER_TMP"
else
  echo "[Filter] 无待过滤项目，跳过。"
fi

# 主循环（统一处理 bulk_first / bulk_followup：A 类优先，B 类补齐）
processed=0
batch_num=0
done_after=0  # cumulative done counter, updated inside the loop; default for empty runs

while [ "$processed" -lt "$TOTAL_PROJECTS" ]; do
  batch_num=$((batch_num + 1))
  remaining=$((TOTAL_PROJECTS - processed))
  this_batch_size=$BATCH_SIZE_PER_CLI
  if [ "$remaining" -lt "$this_batch_size" ]; then
    this_batch_size=$remaining
  fi

  echo ""
  echo "=== Batch $batch_num (target $this_batch_size, processed $processed/$TOTAL_PROJECTS) ==="

  # 统计当前已完成的 bulk 任务数（bulk_first + bulk_followup）
  done_before=$(sqlite3 "$DB" "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND task_type IN ('bulk_first','bulk_followup') AND status='done';")

  # 调度本批任务
  echo "[Batch $batch_num] Scheduling up to $this_batch_size projects..."
  python3 "$STAGES/schedule.py" --mode bulk_first --batch-size "$this_batch_size" || \
    echo "WARN: schedule.py 返回非零退出码。"

  # 获取本批要处理的任务 ID（pending/running/analyzed 的 bulk_first / bulk_followup，A 类优先）
  TASK_IDS=$(sqlite3 "$DB" "
    SELECT id FROM tasks
    WHERE task_date='$DATE'
      AND task_type IN ('bulk_first','bulk_followup')
      AND status IN ('pending','running','analyzed')
    ORDER BY CASE task_type WHEN 'bulk_first' THEN 0 ELSE 1 END,
             CASE status WHEN 'pending' THEN 0 WHEN 'running' THEN 1 ELSE 2 END,
             id
    LIMIT $this_batch_size;
  ")

  if [ -z "$TASK_IDS" ]; then
    echo "[Batch $batch_num] 没有可调度的任务，结束循环。"
    break
  fi

  # 把多行 ID 转成逗号分隔
  TASK_IDS_CSV=$(echo "$TASK_IDS" | tr '\n' ',' | sed 's/,$//')
  echo "[Batch $batch_num] Task IDs: $TASK_IDS_CSV"

  # Step 1: Python 规则分析，生成 draft
  echo "[Batch $batch_num] Running stages/analyze.py..."
  python3 "$STAGES/analyze.py" --date "$DATE" --task-ids "$TASK_IDS_CSV" || \
    echo "WARN: analyze.py 返回非零退出码，部分 draft 可能未生成。"

  # Step 2: CLI 复杂判断（瞬时连接错误重试：第 1 次失败后等 60s，第 2 次失败后等 180s，共 3 次尝试）
  echo "[Batch $batch_num] Running CLI judgment..."
  _ANALYZE_V2_TMP=$(mktemp)
  sed \
    -e "s|/path/to/pipeline/data/pipeline.db|$DB|g" \
    -e "s|ANALYSIS_DATE|$DATE|g" \
    -e "s|TASK_ID_LIST|$TASK_IDS_CSV|g" \
    "$PROMPTS/analyze_v2.md" > "$_ANALYZE_V2_TMP"

  _JUDGE_BACKOFFS=(60 180)   # 第 1 次重试前等 60s，第 2 次重试前等 180s
  _judge_attempt=0
  _judge_ok=0
  while [ "$_judge_attempt" -le "${#_JUDGE_BACKOFFS[@]}" ]; do
    _judge_attempt=$((_judge_attempt + 1))
    [ "$_judge_attempt" -gt 1 ] && echo "[Batch $batch_num] CLI judgment 第 $_judge_attempt 次尝试..."
    if echo "$CLI_TOOL" | grep -qE "cursor-agent|agent"; then
      if eval "$CLI_TOOL" < "$_ANALYZE_V2_TMP"; then _judge_ok=1; break; fi
    else
      if eval "$CLI_TOOL" --print - < "$_ANALYZE_V2_TMP"; then _judge_ok=1; break; fi
    fi
    if [ "$_judge_attempt" -le "${#_JUDGE_BACKOFFS[@]}" ]; then
      _wait=${_JUDGE_BACKOFFS[$((_judge_attempt - 1))]}
      echo "WARN: analyze_v2 第 $_judge_attempt 次失败（退出码非零），${_wait}s 后重试..."
      sleep "$_wait"
    fi
  done
  [ "$_judge_ok" -eq 0 ] && echo "WARN: claude analyze_v2 重试 $(( ${#_JUDGE_BACKOFFS[@]} + 1 )) 次仍失败，部分任务可能未精炼。"
  rm -f "$_ANALYZE_V2_TMP"

  done_after=$(sqlite3 "$DB" "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND task_type IN ('bulk_first','bulk_followup') AND status='done';")
  if [ "$done_after" -eq "$done_before" ]; then
    echo "WARN: 本批没有任务变为 done，避免死循环，结束。"
    break
  fi
  # 修复：processed 应该追踪本次运行处理的数量，而不是累计 done 数。
  # 否则当累计 done 超过 TOTAL_PROJECTS 时，循环会提前退出。
  processed=$((processed + done_after - done_before))
  echo "[Batch $batch_num] Complete. This run: $processed / $TOTAL_PROJECTS; cumulative done: $done_after"
done

# Stage 4.5 + Stage 5
echo ""
echo "=== Scoring and report ==="
python3 "$STAGES/scoring.py" || \
  echo "WARN: scoring.py 返回非零退出码。"
python3 "$STAGES/report.py" --date "$DATE" || \
  echo "WARN: report.py 返回非零退出码。"

# Git push
DONE=$(sqlite3 "$DB" "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status='done';")
SKIPPED=$(sqlite3 "$DB" "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status='skipped';")
REMAINING=$(sqlite3 "$DB" "SELECT COUNT(*) FROM projects WHERE status='bulk_pending';")

git -C "$PIPELINE_DIR" add "$PIPELINE_DIR/data/pipeline.db"
test -f "$PIPELINE_DIR/data/reports/$DATE.md" && \
  git -C "$PIPELINE_DIR" add "$PIPELINE_DIR/data/reports/$DATE.md" || true
# v2 基础设施文件：stages/analyze.py 被 .gitignore 排除，需 force-add
git -C "$PIPELINE_DIR" add -f "$PIPELINE_DIR/run_bulk_v2.sh" || true
git -C "$PIPELINE_DIR" add -f "$PIPELINE_DIR/stages/analyze.py" || true
git -C "$PIPELINE_DIR" add "$PIPELINE_DIR/stages/schedule.py" || true
git -C "$PIPELINE_DIR" add "$PIPELINE_DIR/prompts/analyze_v2.md" || true
git -C "$PIPELINE_DIR" diff --staged --quiet || \
  git -C "$PIPELINE_DIR" commit \
    -m "feat: bulk v2 analysis $DATE (done=$DONE skipped=$SKIPPED remaining=$REMAINING)"

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
[ "$_push_ok" -eq 0 ] && \
  echo "ERROR: git push 连续 3 次失败，请手动推送。"

echo "=== Done === Processed $processed / $TOTAL_PROJECTS projects in this run (cumulative done today: ${done_after:-0})"
