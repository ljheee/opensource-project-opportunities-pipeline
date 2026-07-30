#!/usr/bin/env bash
# 存量回扫：对历史 open 且 value IN (high,medium) 的机会点执行 v3 对抗验证。
# 与 run.sh 内嵌 verify 循环同构；可重复运行直到存量清零。
# 用法: bash run_verify_backlog.sh [每批机会点数=20] [本次总预算=100]
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$PIPELINE_DIR/data/pipeline.db"
PROMPTS="$PIPELINE_DIR/prompts"
STAGES="$PIPELINE_DIR/stages"

if [ -f "$PIPELINE_DIR/.env" ]; then
  set -a; source "$PIPELINE_DIR/.env"; set +a
fi
CLI_TOOL="${CLI_TOOL:-claude --dangerously-skip-permissions}"

BATCH_SIZE=${1:-20}
BUDGET=${2:-100}
for v in "$BATCH_SIZE" "$BUDGET"; do
  if ! [[ "$v" =~ ^[0-9]+$ ]] || [ "$v" -le 0 ]; then
    echo "ERROR: 参数必须为正整数。用法: bash run_verify_backlog.sh [每批=20] [总预算=100]"
    exit 1
  fi
done

# 进程互斥锁（与 run.sh 同款；macOS 无 flock 时降级为警告）
_LOCK_FILE="$PIPELINE_DIR/data/.pipeline.lock"
mkdir -p "$(dirname "$_LOCK_FILE")"
if command -v flock >/dev/null 2>&1; then
  exec 9>"$_LOCK_FILE"
  if ! flock -n 9; then
    echo "ERROR: 另一个 pipeline 实例（run.sh / run_bulk*.sh / run_verify_backlog.sh）正在运行，本次退出。"
    exit 1
  fi
else
  echo "WARN: flock 命令不可用（macOS 环境），跳过进程互斥锁。请勿并发运行多个 pipeline 实例。"
fi

if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "WARN: GITHUB_TOKEN 未设置，verify 核查可能因限流失败。"
fi

REMAIN=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM opportunities WHERE status='open' AND value IN ('high','medium');")
echo "=== verify backlog: 存量 $REMAIN 条，本次预算 $BUDGET 条，每批 $BATCH_SIZE ==="

all_opp_ids=""
processed=0
while [ "$processed" -lt "$BUDGET" ]; do
  batch=$BATCH_SIZE
  remaining_budget=$((BUDGET - processed))
  [ "$remaining_budget" -lt "$batch" ] && batch=$remaining_budget

  opp_ids=$(sqlite3 "$DB" "
    SELECT o.id FROM opportunities o
    JOIN projects p ON p.id = o.project_id
    WHERE o.status='open' AND o.value IN ('high','medium')
    ORDER BY CASE o.value WHEN 'high' THEN 0 ELSE 1 END, p.stars DESC, o.id
    LIMIT $batch;")
  if [ -z "$opp_ids" ]; then
    echo "存量队列已清空。"
    break
  fi

  opp_csv=$(echo "$opp_ids" | tr '\n' ',' | sed 's/,$//')
  mkdir -p "$PIPELINE_DIR/data/verify_log"
  pending_file="$PIPELINE_DIR/data/verify_log/.pending_$(date -u +%Y%m%dT%H%M%S).json"
  _VERIFY_TMP=$(mktemp)
  sed -e "s|/path/to/pipeline/data/pipeline.db|$DB|g" \
      -e "s|OPP_ID_LIST|$opp_csv|g" \
      -e "s|PENDING_FILE|$pending_file|g" \
      "$PROMPTS/verify_v3.md" > "$_VERIFY_TMP"

  _backoffs=(60 180) _attempt=0 _ok=0
  while [ "$_attempt" -le "${#_backoffs[@]}" ]; do
    _attempt=$((_attempt + 1))
    [ "$_attempt" -gt 1 ] && echo "[backlog] verify 第 $_attempt 次尝试..."
    if echo "$CLI_TOOL" | grep -qE "cursor-agent|agent"; then
      if eval "$CLI_TOOL" < "$_VERIFY_TMP"; then _ok=1; break; fi
    else
      if eval "$CLI_TOOL" --print - < "$_VERIFY_TMP"; then _ok=1; break; fi
    fi
    if [ "$_attempt" -le "${#_backoffs[@]}" ]; then
      echo "WARN: verify 第 $_attempt 次失败，${_backoffs[$((_attempt - 1))]}s 后重试..."
      sleep "${_backoffs[$((_attempt - 1))]}"
    fi
  done
  rm -f "$_VERIFY_TMP"
  if [ "$_ok" -eq 0 ]; then
    echo "WARN: verify 重试 3 次仍失败，本批停留 open，本次运行结束（防死循环）。"
    break
  fi

  python3 "$STAGES/verify_ingest.py" "$pending_file" --opp-ids "$opp_csv" || \
    echo "WARN: verify_ingest 返回非零退出码。"
  # 只把本批已被裁决（verified/refuted）的 id 交给 validate：LLM 漏判的行停留 open，
  # 若并入 scope 会被 validate 的 check5 误 refute（check5 仅豁免 verified）。
  judged_ids=$(sqlite3 "$DB" \
    "SELECT id FROM opportunities WHERE id IN ($opp_csv) AND status IN ('verified','refuted');" \
    | tr '\n' ',' | sed 's/,$//')
  all_opp_ids="${all_opp_ids:+$all_opp_ids,}$judged_ids"
  processed=$((processed + $(echo "$opp_ids" | wc -l | tr -d ' ')))
  echo "[backlog] 累计处理 $processed / $BUDGET"
done

if [ "$processed" -gt 0 ]; then
  echo "[backlog] 机器核账 + 复评..."
  python3 "$STAGES/validate.py" --opp-ids "$all_opp_ids" || \
    echo "WARN: validate.py 返回非零退出码。"
  python3 "$STAGES/scoring.py" || \
    echo "WARN: scoring 复评返回非零退出码。"
fi

DATE=$(date -u +%Y-%m-%d)
git -C "$PIPELINE_DIR" add "$PIPELINE_DIR/data/pipeline.db"
git -C "$PIPELINE_DIR" add "$PIPELINE_DIR/data/verify_log" 2>/dev/null || true
git -C "$PIPELINE_DIR" diff --staged --quiet || \
  git -C "$PIPELINE_DIR" commit -m "chore: verify backlog $DATE (processed=$processed)"

_push_ok=0
for _i in 1 2 3; do
  if git -C "$PIPELINE_DIR" push; then _push_ok=1; break; fi
  echo "WARN: git push 失败（attempt $_i/3），10 秒后 pull --rebase 再试..."
  sleep 10
  git -C "$PIPELINE_DIR" pull --rebase || true
done
[ "$_push_ok" -eq 0 ] && \
  echo "ERROR: git push 连续 3 次失败，请手动推送：cd $PIPELINE_DIR && git pull --rebase && git push"

LEFT=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM opportunities WHERE status='open' AND value IN ('high','medium');")
echo "=== 完成 === 本次处理 $processed 条；剩余待验证 $LEFT 条"
