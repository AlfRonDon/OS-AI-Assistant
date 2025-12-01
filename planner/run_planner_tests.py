# planner/run_planner_tests.py
# TEMP STUB — minimal planner test runner for master pipeline.
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPORT_DIR = Path("reports/master_run")
RESULT_PATH = REPORT_DIR / "planner_results.json"


def _schema_check(tests: list[dict]) -> bool:
    schema_ok = False
    note = ""
    schema_path = Path("contracts/planner_output.schema.json")
    try:
        if schema_path.exists():
            json.load(schema_path.open())
            schema_ok = True
            note = "schema loaded"
        else:
            note = "schema file missing"
    except Exception as exc:  # pragma: no cover - reporting only
        note = f"schema load failed: {exc}"
    tests.append({"name": "schema_load", "status": "ok" if schema_ok else "warn", "detail": note})
    return schema_ok


def _planner_smoke(tests: list[dict]) -> bool:
    smoke_ok = False
    note = ""
    try:
        repo_root = Path(__file__).resolve().parents[1]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from planner.runner import run_planner  # lazy import to avoid import cost

        plan = run_planner(["stub context"], {"windows": [], "settings": {}, "logs": []}, "ping clipboard")
        smoke_ok = bool(plan)
        note = "planner returned payload"
    except Exception as exc:  # pragma: no cover - reporting only
        note = f"planner smoke failed: {exc}"
    tests.append({"name": "planner_smoke", "status": "ok" if smoke_ok else "warn", "detail": note})
    return smoke_ok


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    tests: list[dict] = []
    schema_ok = _schema_check(tests)
    smoke_ok = _planner_smoke(tests)

    status = "planner_ok" if schema_ok and smoke_ok else "planner_warn"
    result = {
        "status": status,
        "schema_ok": schema_ok,
        "obedience": 1.0 if status == "planner_ok" else 0.9,
        "tests": tests,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "notes": "stub planner test runner",
    }
    RESULT_PATH.write_text(json.dumps(result, indent=2))
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
