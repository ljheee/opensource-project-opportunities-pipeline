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

# judge 的最终文字总结可能很长（20 行逐条证据 + 限定说明 + 记忆沉淀）。输出上限太低时
# 会话会在**写总结那一刻**以 "response exceeded the maximum output tokens" 失败，
# 整批白跑（2026-10-21 实测：继承 8192 上限的会话在第 6 批因此失败两次，
# 每次重试都要重做 30 分钟的取证）。取一个下限，不覆盖更高的用户设置。
if [ "${CLAUDE_CODE_MAX_OUTPUT_TOKENS:-0}" -lt 32768 ] 2>/dev/null; then
  export CLAUDE_CODE_MAX_OUTPUT_TOKENS=32768
fi

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


# ── 看门狗 ───────────────────────────────────────────────────────────────────
# verify 会话可能**静默挂死**：2026-10-21 实测单批挂 2 小时、20 条一行未写。
# 脚本原本的重试只在 CLI 非零退出时触发，而挂死的进程不会退出 → 整轮卡住。
# 改为：后台跑 CLI，同时轮询本批行的 status 变化（verify prompt 每条裁决写库后
# 立即 commit，所以行状态变化就是真实进度）。连续 ${VERIFY_STALL_MINUTES} 分钟
# 无进展就杀掉进程，交给已有的重试逻辑。
VERIFY_STALL_MINUTES="${VERIFY_STALL_MINUTES:-15}"

_count_judged() {
  local _csv="$1"
  sqlite3 "$DB" "SELECT COUNT(*) FROM opportunities
                 WHERE id IN ($_csv) AND status IN ('verified','refuted');"
}

_run_verify_watchdog() {
  local _prompt="$1" _csv="$2" _out="$3"
  local _prev _now _idle=0 _pid _rc
  _prev=$(_count_judged "$_csv")

  if echo "$CLI_TOOL" | grep -qE "cursor-agent|agent"; then
    eval "$CLI_TOOL" < "$_prompt" > "$_out" 2>&1 &
  else
    # --output-format stream-json：会话的每个事件**实时**落盘，于是「输出文件在长」
    # 就是可靠的心跳。纯 --print 只在会话结束时才吐字，健康的重批（先做 40 分钟
    # code search 再一次性写库）和挂死的会话在文本上完全一样。
    eval "$CLI_TOOL" --print --output-format stream-json --verbose - < "$_prompt" > "$_out" 2>&1 &
  fi
  _pid=$!

  local _size_prev _size_now
  _size_prev=$(wc -c < "$_out" 2>/dev/null || echo 0)
  while kill -0 "$_pid" 2>/dev/null; do
    sleep 30
    _size_now=$(wc -c < "$_out" 2>/dev/null || echo 0)
    _now=$(_count_judged "$_csv")
    if [ "$_now" -gt "$_prev" ] || [ "$_size_now" -gt "$_size_prev" ]; then
      # 两种进展都算活着：写库（真实进度）或输出在长（会话在干活）
      _prev=$_now
      _size_prev=$_size_now
      _idle=0
      continue
    fi
    _idle=$((_idle + 1))
    if [ "$_idle" -ge $((VERIFY_STALL_MINUTES * 2)) ]; then
      echo "WARN: verify 会话 ${VERIFY_STALL_MINUTES} 分钟无进展（输出未增长、本批已裁决 ${_prev} 条），杀掉后重试"
      pkill -P "$_pid" 2>/dev/null
      kill "$_pid" 2>/dev/null
      sleep 3
      pkill -9 -P "$_pid" 2>/dev/null
      kill -9 "$_pid" 2>/dev/null
      wait "$_pid" 2>/dev/null
      _dump_verify_output "$_out"
      return 1
    fi
  done
  wait "$_pid"
  _rc=$?
  _dump_verify_output "$_out"
  return $_rc
}

# stream-json 的最后一条 assistant 消息就是 judge 的结论文本；整份 JSON 事件流对人
# 不可读，只把结论文本打进日志。
_dump_verify_output() {
  local _f="$1"
  [ -s "$_f" ] || return 0
  python3 - "$_f" <<'PYEOF' 2>/dev/null || tail -5 "$_f"
import json, sys
last = ""
for line in open(sys.argv[1]):
    try:
        d = json.loads(line)
    except Exception:
        continue
    if d.get("type") == "assistant":
        c = (d.get("message") or {}).get("content")
        if isinstance(c, list):
            t = "".join(b.get("text", "") for b in c if isinstance(b, dict))
            if t.strip():
                last = t
print(last)
PYEOF
}

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
    if _run_verify_watchdog "$_VERIFY_TMP" "$opp_csv" "/tmp/verify_backlog_out.$$"; then
      _ok=1; break
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
  echo "WARN: git push 失败（attempt $_i/3），10 秒后重试..."
  sleep 10
done
if [ "$_push_ok" -eq 0 ]; then
  # 不自动 pull --rebase：data/pipeline.db 是二进制文件，两边都改过时 rebase 会
  # 留下冲突的 rebase 状态（`|| true` 还会把失败吞掉），比推送失败更难收拾。
  echo "ERROR: git push 连续 3 次失败，请手动合并后推送："
  echo "       git -C \"$PIPELINE_DIR\" pull --no-rebase"
  echo "       # 解决 data/pipeline.db 冲突（按表取并集）后 git add && git push"
  echo "       远端可能已有新提交（daily discover 只加项目/任务/发现日志），需手工按表取并集合并。"
fi

LEFT=$(sqlite3 "$DB" \
  "SELECT COUNT(*) FROM opportunities WHERE status='open' AND value IN ('high','medium');")
echo "=== 完成 === 本次处理 $processed 条；剩余待验证 $LEFT 条"
