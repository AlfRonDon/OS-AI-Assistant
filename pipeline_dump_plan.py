#!/usr/bin/env python3
"""Wrapper to dump pipeline plans without execution."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# PATH QUOTE HELPERS - inserted by automation
import shlex, platform, subprocess as _subprocess
IS_WINDOWS = platform.system() == "Windows"

def qpath_for_shell(p: str) -> str:
    p = str(p)
    return f'"{p}"' if IS_WINDOWS else shlex.quote(p)

def run_cmd_safe_list(args_list, cwd=None, env=None):
    'Run subprocess with list args (no shell). Returns CompletedProcess-like object attributes.'
    try:
        p = _subprocess.run(args_list, shell=False, capture_output=True, text=True, cwd=cwd, env=env)
        return p
    except Exception as e:
        # emulate a CompletedProcess for error handling
        class Dummy:
            def __init__(self):
                self.returncode = 99
                self.stdout = ""
                self.stderr = str(e)
        return Dummy()



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump normalized pipeline plan without executing.")
    parser.add_argument("--task", required=True, nargs="+", help="Path to task JSON")
    args = parser.parse_args(argv)
    task_arg = " ".join(args.task)
    task_path = Path(task_arg)
    if not task_path.exists():
        print(f"task not found: {task_path}", file=sys.stderr)
        return 1
    cmd = [sys.executable, 'pipeline_runner.py', '--task', str(task_path), '--dump-plan-only']
    result = run_cmd_safe_list(cmd)
    return result.returncode


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())