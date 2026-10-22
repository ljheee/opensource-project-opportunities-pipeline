#!/usr/bin/env python3
"""Smoke tests for lib/pipeline_watchdog.sh.

2026-10-21: a verify session hung for 2h6m with zero writes — alive, silent, and
indistinguishable from a healthy long batch under `claude --print` (which only
emits text when the session ends). The watchdog separates the two cases with two
signals: the output stream growing, and a business-write probe.

These tests drive the real shell function with a fake CLI, so they cover the
actual kill path (child processes included) rather than a re-implementation.
"""
import os
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(REPO, "lib", "pipeline_watchdog.sh")


def _run(script: str, timeout: int = 60):
    """Run a bash snippet with the watchdog lib sourced in."""
    harness = (
        "set -uo pipefail\n"
        f'DB="{REPO}/data/pipeline.db"\n'
        ". lib/pipeline_watchdog.sh\n"
        + script
    )
    return subprocess.run(["bash", "-c", harness], capture_output=True, text=True,
                          timeout=timeout, cwd=REPO)


class TestWatchdog(unittest.TestCase):
    def test_silent_session_is_killed(self):
        """A CLI that never writes anything must be killed and reported as failure."""
        script = (
            "CLI_TOOL=\"sh -c 'sleep 300' --\"\n"
            "WATCHDOG_STALL_MINUTES=1\n"
            "WATCHDOG_POLL_SECONDS=1\n"
            "_llm_with_watchdog /dev/null /tmp/wd_test_silent.txt 'SELECT 1'\n"
            "echo \"rc=$?\"\n"
        )
        out = _run(script, timeout=90)
        self.assertIn("rc=1", out.stdout, out.stderr)
        self.assertIn("无进展", out.stderr)

    def test_live_output_is_not_killed(self):
        """A CLI that keeps producing output must survive the stall threshold."""
        script = (
            "CLI_TOOL=\"sh -c 'while true; do echo tick; sleep 2; done' --\"\n"
            "WATCHDOG_STALL_MINUTES=1\n"
            "WATCHDOG_POLL_SECONDS=1\n"
            "_llm_with_watchdog /dev/null /tmp/wd_test_live.txt 'SELECT 1' &\n"
            "WP=$!\n"
            "sleep 8\n"
            "if kill -0 $WP 2>/dev/null; then echo ALIVE; else echo DEAD; fi\n"
            "kill $WP 2>/dev/null; pkill -f 'while true' 2>/dev/null\n"
        )
        out = _run(script, timeout=60)
        self.assertIn("ALIVE", out.stdout, out.stderr)

    def test_surviving_cli_exit_code_is_propagated(self):
        """A non-zero CLI exit must reach the caller so the retry logic fires."""
        script = (
            "CLI_TOOL=\"sh -c 'exit 3' --\"\n"
            "WATCHDOG_STALL_MINUTES=1\n"
            "WATCHDOG_POLL_SECONDS=1\n"
            "_llm_with_watchdog /dev/null /tmp/wd_test_rc.txt 'SELECT 1'\n"
            "echo \"rc=$?\"\n"
        )
        out = _run(script, timeout=60)
        self.assertIn("rc=3", out.stdout, out.stderr)

    def test_probe_counts_rows_and_tolerates_bad_sql(self):
        """The probe is best-effort: it always exits 0 and prints an integer.

        A broken probe must not abort the script (`set -e` is active in the runners);
        it degrades to a constant 0, which means "no progress signal" — the
        output-stream signal still keeps the session alive.
        """
        script = (
            "_watchdog_probe 'SELECT COUNT(*) FROM opportunities' | grep -E '^[0-9]+$' >/dev/null "
            "&& echo PROBE_OK\n"
            "_watchdog_probe 'SELECT * FROM no_such_table' > /tmp/wd_probe_bad.txt; "
            "echo \"rc=$? val=$(cat /tmp/wd_probe_bad.txt)\"\n"
            "_watchdog_probe '-' | grep -qx 0 && echo DASH_OK\n"
        )
        out = _run(script, timeout=30)
        self.assertIn("PROBE_OK", out.stdout, out.stderr)
        self.assertIn("rc=0 val=0", out.stdout, out.stderr)
        self.assertIn("DASH_OK", out.stdout, out.stderr)


class TestRunnerScriptsUseTheWatchdog(unittest.TestCase):
    """The refine stage of the daily runners must not call the CLI bare.

    A bare `eval "$CLI_TOOL" --print -` can hang forever: the retry only fires on a
    non-zero exit, and a hung process never exits.
    """

    def test_refine_stages_go_through_the_watchdog(self):
        for f in ("run.sh", "run_bulk_v2.sh"):
            with self.subTest(script=f):
                with open(os.path.join(REPO, f)) as fh:
                    src = fh.read()
                self.assertIn("pipeline_watchdog.sh", src,
                              f"{f} 没有 source 共用看门狗")
                self.assertIn("_llm_with_watchdog", src,
                              f"{f} 的精炼阶段没有走看门狗")

    def test_bare_print_call_is_gone(self):
        for f in ("run.sh", "run_bulk_v2.sh"):
            with self.subTest(script=f):
                with open(os.path.join(REPO, f)) as fh:
                    src = fh.read()
                self.assertNotIn('eval "$CLI_TOOL" --print - <', src,
                                 f"{f} 仍有裸的 CLI 调用（会静默挂死）")
