#!/usr/bin/env python3
"""Wrapper to dump pipeline plans without execution."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump normalized pipeline plan without executing.")
    parser.add_argument("--task", required=True, nargs="+", help="Path to task JSON")
    args = parser.parse_args(argv)
    task_arg = " ".join(args.task)
    task_path = Path(task_arg)
    if not task_path.exists():
        print(f"task not found: {task_path}", file=sys.stderr)
        return 1
    cmd = f"python pipeline_runner.py --task \"{task_path}\" --dump-plan-only"
    return subprocess.call(cmd, shell=True)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
