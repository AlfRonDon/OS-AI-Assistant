#!/usr/bin/env python3
"""
Lightweight smoke test for the remote planner adapter.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from planner.remote_adapter import call_remote_planner, minimal_sanity_check  # noqa: E402


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "Plan how to organize notes about this workspace."
    retrieval_snippets = [
        {"id": "workspace", "snippet": "Workspace includes planner, mock_os, and retrieval packages."},
        {"id": "api_calls", "snippet": "Planners emit step_label, api_call, args, expected_state fields."},
    ]
    state_snapshot = {
        "windows": [{"id": "win-1", "title": "Home", "active": True}],
        "clipboard": None,
        "settings": {},
    }

    result = call_remote_planner(retrieval_snippets, state_snapshot, query)
    output_path = ROOT / "reports" / "remote_planner_test.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {output_path} (valid={minimal_sanity_check(result)})")


if __name__ == "__main__":
    main()
