#!/usr/bin/env bash
# ── 共用：LLM 会话看门狗 ─────────────────────────────────────────────────────
# 由 run.sh / run_bulk_v2.sh / run_verify_backlog.sh 共同 source。
#
# **背景（2026-10-21 实测）**：LLM 会话可能**静默挂死**——进程活着、不报错、
# 但一行数据库都不写（单批挂了 2 小时 6 分钟，20 条机会点 status 全是 open）。
# 脚本原有的重试只在 CLI **非零退出**时触发，而挂死的进程不会退出 → 整轮卡死，
# 既不前进也不报错。
#
# **判活用双信号，缺一不可**：
#   1. **输出流在增长**——CLI 用 `--output-format stream-json --verbose`，每个事件
#      实时落盘（实测 20 秒写 55KB），所以「文件在长」= 会话在干活。
#      只看纯 `--print` 不行：它只在**会话结束**时吐字，健康的重批和真挂死在文本上
#      完全一样（judge 先做 30–60 分钟 code search 再一次性写库，这期间零输出）。
#   2. **探针 SQL 的返回值在变化**——业务写入进度。
#      只看 (2) 会误杀「长时间取证后一次性写库」的健康批次（已实测误杀两次）。
#
# 用法：`_llm_with_watchdog <prompt_file> <out_file> <probe_sql> [extra_cli_args...]`
#   probe_sql：返回**一列整数**的 SQL（进度探针）；传 `-` 表示没有探针。
#   返回：CLI 的退出码；被看门狗杀掉时返回 1。
#
# 调用方必须用 `if _llm_with_watchdog ...; then` 的形式调用——`if` 条件里
# `set -e` 会被挂起，函数内部的非零返回才不会中止整个脚本。
#
# 需要调用方提供：CLI_TOOL、DB。
# 可选：WATCHDOG_STALL_MINUTES（默认 15 分钟无进展即判定挂死）。

WATCHDOG_STALL_MINUTES="${WATCHDOG_STALL_MINUTES:-15}"
# 轮询间隔：单测要把它调到 1 秒，否则「静默挂死」那例要等 30 秒。
WATCHDOG_POLL_SECONDS="${WATCHDOG_POLL_SECONDS:-30}"

# 进度探针：返回一列整数。SQL 失败时返回 0（探针不可用时只靠输出流信号判活）。
_watchdog_probe() {
  local _sql="$1"
  [ "$_sql" = "-" ] && { echo 0; return 0; }
  sqlite3 "$DB" "$_sql" 2>/dev/null || echo 0
}

# 判断 CLI 命令形态：cursor-agent 系不吃 claude 的 --print/--output-format 参数。
_watchdog_cli_is_cursor() {
  echo "$CLI_TOOL" | grep -qE "cursor-agent|agent"
}

# 日志里区分是哪种 CLI（原来的告警消息会区分）。
_watchdog_cli_label() {
  if _watchdog_cli_is_cursor; then echo "agent"; else echo "claude"; fi
}

# 把 judge 的结论文本（stream-json 里最后一条 assistant 消息）打进日志，
# 整份事件流对人不可读。
_watchdog_dump_output() {
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

_llm_with_watchdog() {
  local _prompt="$1" _out="$2" _probe="$3"
  shift 3
  local _pid _rc=0 _idle=0
  local _size_prev _size_now _probe_prev _probe_now

  if _watchdog_cli_is_cursor; then
    eval "$CLI_TOOL" "$@" < "$_prompt" > "$_out" 2>&1 &
  else
    eval "$CLI_TOOL" --print --output-format stream-json --verbose "$@" - < "$_prompt" > "$_out" 2>&1 &
  fi
  _pid=$!

  _size_prev=$(wc -c < "$_out" 2>/dev/null || echo 0)
  _probe_prev=$(_watchdog_probe "$_probe")

  while kill -0 "$_pid" 2>/dev/null; do
    sleep "$WATCHDOG_POLL_SECONDS"
    _size_now=$(wc -c < "$_out" 2>/dev/null || echo 0)
    _probe_now=$(_watchdog_probe "$_probe")
    if [ "$_size_now" -gt "$_size_prev" ] || [ "$_probe_now" != "$_probe_prev" ]; then
      _size_prev=$_size_now
      _probe_prev=$_probe_now
      _idle=0
      continue
    fi
    _idle=$((_idle + 1))
    if [ "$_idle" -ge $((WATCHDOG_STALL_MINUTES * 2)) ]; then
      echo "WARN: LLM 会话 ${WATCHDOG_STALL_MINUTES} 分钟无进展（输出未增长、探针无变化），杀掉后重试" >&2
      pkill -P "$_pid" 2>/dev/null || true
      kill "$_pid" 2>/dev/null || true
      sleep 3
      pkill -9 -P "$_pid" 2>/dev/null || true
      kill -9 "$_pid" 2>/dev/null || true
      wait "$_pid" 2>/dev/null || true
      _watchdog_dump_output "$_out"
      return 1
    fi
  done

  wait "$_pid" || _rc=$?
  _watchdog_dump_output "$_out"
  return $_rc
}
