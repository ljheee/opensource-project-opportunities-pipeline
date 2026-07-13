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

# 参数：<本次最多处理项目数> <每次 CLI 判断的任务数>，语义与 run_bulk_v2.sh 一致
# 不带参数时默认处理最多 200 个、每批 5 个（日常增量通常远小于此，自然全部处理完）
TOTAL_PROJECTS=${1:-200}
BATCH_SIZE_PER_CLI=${2:-5}

if ! [[ "$TOTAL_PROJECTS" =~ ^[0-9]+$ ]] || [ "$TOTAL_PROJECTS" -le 0 ] || [ "$TOTAL_PROJECTS" -gt 1000 ]; then
  echo "ERROR: TOTAL_PROJECTS 必须为 1~1000 之间的正整数，当前值: '$TOTAL_PROJECTS'"
  echo "用法: bash run.sh [总项目数] [每CLI任务数]"
  exit 1
fi
if ! [[ "$BATCH_SIZE_PER_CLI" =~ ^[0-9]+$ ]] || [ "$BATCH_SIZE_PER_CLI" -le 0 ] || [ "$BATCH_SIZE_PER_CLI" -gt 50 ]; then
  echo "ERROR: BATCH_SIZE_PER_CLI 必须为 1~50 之间的正整数，当前值: '$BATCH_SIZE_PER_CLI'"
  exit 1
fi

echo "=== GitHub Opportunities Pipeline - $DATE (total=$TOTAL_PROJECTS, batch_size=$BATCH_SIZE_PER_CLI) ==="

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

# 把跨天遗留的任务（pending/running/analyzed）归到当天，统一交给本次运行处理。
# 必须在 reset 块之前执行：否则跨天 analyzed 任务（task_date 仍是昨天）无法被
# reset 块的 "task_date='今天' AND status='analyzed'" 识别，项目会被误降级为 bulk_pending。
# 注意去重：同一 (project_id, task_type) 可能存在多条跨天遗留任务（schedule 只按当天
# 去重，历史 pending 不阻止新任务），直接 UPDATE 会撞 UNIQUE(project_id, task_date, task_type)。
# 处理顺序：①同组只留最新一条，其余标 skipped；②与今天已有任务冲突的标 skipped；③迁移剩余。
sqlite3 "$DB" "
  UPDATE tasks
  SET status='skipped', finished_at=strftime('%Y-%m-%dT%H:%M:%S+00:00','now')
  WHERE status IN ('pending','running','analyzed')
    AND task_date < '$DATE'
    AND id NOT IN (
      SELECT MAX(id) FROM tasks
      WHERE status IN ('pending','running','analyzed') AND task_date < '$DATE'
      GROUP BY project_id, task_type
    );

  UPDATE tasks
  SET status='skipped', finished_at=strftime('%Y-%m-%dT%H:%M:%S+00:00','now')
  WHERE status IN ('pending','running','analyzed')
    AND task_date < '$DATE'
    AND EXISTS (
      SELECT 1 FROM tasks t2
      WHERE t2.project_id = tasks.project_id
        AND t2.task_type = tasks.task_type
        AND t2.task_date = '$DATE'
    );

  UPDATE tasks
  SET task_date='$DATE'
  WHERE status IN ('pending','running','analyzed')
    AND task_date < '$DATE';
"

# 将上次中途崩溃卡在 analyzing 状态的项目重置，使其可被重新调度
# 优先级1：有已完成任务的项目 → 曾经是 active，重置回 active
# 优先级2：有 triggered/incremental 类型任务（task_type 说明原本是 active）→ 重置回 active
# 优先级3：任务为 analyzed（等待 CLI 判断）→ 保持 analyzing，本次运行继续交给 CLI
# 优先级4：其余 → 首次分析未完成，重置回 bulk_pending
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
        echo "WARN: agent filter 返回非零退出码（round=${_filter_rounds}），本轮跳过，剩余项目留待下次重试。"
        break
      }
    else
      eval "$CLI_TOOL" --print - < "$_FILTER_TMP" || {
        echo "WARN: claude filter 返回非零退出码（round=${_filter_rounds}），本轮跳过，剩余项目留待下次重试。"
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
# analyzed 状态的任务（等待 CLI 判断）也需要继续处理
PENDING=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status IN ('pending','running','analyzed');")

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

echo "今日待分析任务：$PENDING 个（本次最多处理 ${TOTAL_PROJECTS}，每批 ${BATCH_SIZE_PER_CLI} 个塞 CLI）"

# 3. Stage 4: 深层分析（v2 两阶段，批量循环：每批 BATCH_SIZE_PER_CLI 个任务一次 CLI）
# 注意：调度已在循环前一次性完成。incremental 模式每跑一次 schedule 都会新增任务，
# 绝不能放进循环里，否则任务会无限增生。
processed=0
batch_num=0
done_after=0  # 累计 done 计数，循环内更新；空跑时给结尾兜底

while [ "$processed" -lt "$TOTAL_PROJECTS" ]; do
  batch_num=$((batch_num + 1))
  remaining=$((TOTAL_PROJECTS - processed))
  this_batch_size=$BATCH_SIZE_PER_CLI
  if [ "$remaining" -lt "$this_batch_size" ]; then
    this_batch_size=$remaining
  fi

  echo ""
  echo "=== Batch $batch_num (target $this_batch_size, processed $processed/$TOTAL_PROJECTS) ==="

  done_before=$(sqlite3 "$DB" \
    "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status='done';")

  TASK_IDS=$(sqlite3 "$DB" "
    SELECT id FROM tasks
    WHERE task_date='$DATE'
      AND status IN ('pending','running','analyzed')
    ORDER BY CASE task_type WHEN 'triggered' THEN 0 WHEN 'incremental' THEN 1
                            WHEN 'bulk_first' THEN 2 ELSE 3 END,
             CASE status WHEN 'pending' THEN 0 WHEN 'running' THEN 1 ELSE 2 END,
             id
    LIMIT $this_batch_size;
  ")

  if [ -z "$TASK_IDS" ]; then
    echo "[Batch $batch_num] 没有待处理任务，结束循环。"
    break
  fi

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
  [ "$_judge_ok" -eq 0 ] && \
    echo "WARN: analyze_v2 重试 $(( ${#_JUDGE_BACKOFFS[@]} + 1 )) 次仍失败，任务保留在 analyzed 状态，下次运行自动续处理。"
  rm -f "$_ANALYZE_V2_TMP"

  done_after=$(sqlite3 "$DB" \
    "SELECT COUNT(*) FROM tasks WHERE task_date='$DATE' AND status='done';")
  if [ "$done_after" -eq "$done_before" ]; then
    echo "WARN: 本批没有任务变为 done，避免死循环，结束。"
    break
  fi
  processed=$((processed + done_after - done_before))
  echo "[Batch $batch_num] Complete. This run: $processed / $TOTAL_PROJECTS; cumulative done: $done_after"
done

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
# v2 基础设施文件：stages/analyze.py 被 .gitignore 排除，需 force-add
git -C "$PIPELINE_DIR" add -f "$PIPELINE_DIR/stages/analyze.py" || true
git -C "$PIPELINE_DIR" add "$PIPELINE_DIR/stages/schedule.py" || true
git -C "$PIPELINE_DIR" add "$PIPELINE_DIR/prompts/analyze_v2.md" || true

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

echo "=== 完成 === 本次处理 ${processed:-0} / $TOTAL_PROJECTS 个项目（今日累计 done: ${done_after:-0}）"
echo "报告：$PIPELINE_DIR/data/reports/$DATE.md"
