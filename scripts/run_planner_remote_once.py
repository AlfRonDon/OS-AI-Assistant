#!/usr/bin/env python3
"""
Lightweight smoke test for the remote planner adapter by running through planner.runner.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from planner.remote_adapter import minimal_sanity_check  # noqa: E402
from planner.runner import run_planner  # noqa: E402


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "Plan how to organize notes about this workspace."
    retrieval_snippets = [
        "Workspace includes planner, mock_os, and retrieval packages.",
        "Planners emit step_label, api_call, args, expected_state fields.",
    ]
    state_snapshot = {
        "windows": [{"id": "win-1", "title": "Home", "active": True}],
        "clipboard": None,
        "settings": {},
    }

    os.environ.setdefault("USE_REMOTE_MODEL", "1")
    os.environ.setdefault("GPT_OSS_MODEL_PATH", "models/nonexistent.gguf")
    os.environ.setdefault("LLAMA_MODEL_PATH", "models/nonexistent.gguf")
    plan = run_planner(retrieval_snippets, state_snapshot, query)
    serializable_plan = plan.model_dump() if hasattr(plan, "model_dump") else plan
    output_path = ROOT / "reports" / "remote_planner_test.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(serializable_plan, indent=2), encoding="utf-8")
    print(f"Wrote {output_path} (valid={minimal_sanity_check(serializable_plan)})")


if __name__ == "__main__":
    main()
