from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPORT_PATH = Path("reports") / "flaky.json"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_pytest(args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, text=True, capture_output=True)


def parse_total(output: str) -> int:
    match = re.search(r"collected\s+(\d+)\s+items?", output)
    return int(match.group(1)) if match else 0


def load_last_failed() -> List[str]:
    cache_path = Path(".pytest_cache") / "v" / "cache" / "lastfailed"
    if not cache_path.exists():
        return []
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, dict):
        return list(data.keys())
    return []


def build_rerun_cmd(base_args: List[str], nodeid: str) -> List[str]:
    if not base_args:
        return ["pytest", nodeid]
    executable = base_args[0]
    flags = [arg for arg in base_args[1:] if arg.startswith("-")]
    return [executable, nodeid] + flags


def main() -> int:
    base_args = sys.argv[1:]
    if not base_args:
        print("Usage: python tests/utils/flaky_runner.py pytest <args>", file=sys.stderr)
        return 1

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    initial = run_pytest(base_args)
    total = parse_total(initial.stdout + initial.stderr)
    failed_tests = load_last_failed()

    flakes: List[Dict[str, Any]] = []
    per_test: Dict[str, Any] = {}
    final_failures: List[str] = []

    for nodeid in failed_tests:
        retries = 0
        final_rc = 1
        for attempt in range(2):
            retries += 1
            rerun_cmd = build_rerun_cmd(base_args, nodeid)
            result = run_pytest(rerun_cmd)
            final_rc = result.returncode
            per_test[nodeid] = {"initial_rc": 1, "retries": retries, "final_rc": final_rc}
            if final_rc == 0:
                flakes.append({"test": nodeid, "initial_rc": 1, "retries": retries, "final_rc": final_rc})
                break
        if final_rc != 0:
            final_failures.append(nodeid)

    report = {
        "timestamp": utc_timestamp(),
        "total": total,
        "failures_initial": len(failed_tests),
        "flakes": flakes,
        "per_test": per_test,
        "initial_rc": initial.returncode,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if initial.stdout:
        Path("reports/flaky_stdout.log").write_text(initial.stdout, encoding="utf-8")
    if initial.stderr:
        Path("reports/flaky_stderr.log").write_text(initial.stderr, encoding="utf-8")

    if final_failures:
        print(f"Flaky runner detected failures after retries: {', '.join(final_failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
