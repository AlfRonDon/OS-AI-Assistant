# executor/mock_runner.py
# TEMP STUB — lightweight executor mock to satisfy master pipeline.
from __future__ import annotations

import json
import time
from pathlib import Path

REPORT_DIR = Path("reports/master_run")
RESULT_PATH = REPORT_DIR / "executor_result.json"


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "executor_ok",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "stub executor run completed",
        "metrics": {"tasks_executed": 0, "warnings": 0},
    }
    RESULT_PATH.write_text(json.dumps(payload, indent=2))
    print("executor_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
