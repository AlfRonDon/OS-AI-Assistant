#!/usr/bin/env python3
"""
Exercise the remote planner path and record the output.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from planner import remote_adapter  # noqa: E402
from planner.runner import run_planner  # noqa: E402


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "Check remote planner wiring."
    retrieval_snippets = [
        "Remote planner smoke test driven via USE_REMOTE_MODEL.",
        "Planner steps require step_label, api_call, args, expected_state fields.",
    ]
    state_snapshot = {
        "windows": [{"id": "win-1", "title": "Home", "active": True}],
        "clipboard": None,
        "settings": {},
        "logs": [],
    }

    use_remote_env = os.getenv("USE_REMOTE_MODEL")
    effective_remote = use_remote_env if use_remote_env is not None else "1"
    use_remote = effective_remote.strip() == "1"
    if use_remote_env is None:
        os.environ["USE_REMOTE_MODEL"] = "1"

    remote_result = None
    if use_remote:
        try:
            remote_result = remote_adapter.call_remote_planner(retrieval_snippets, state_snapshot, query)
        except Exception as exc:  # pragma: no cover - smoke safeguard
            remote_result = {"error": f"REMOTE_CALL_FAIL: {exc}"}
        remote_adapter.call_remote_planner = lambda *_args, **_kwargs: remote_result

    plan = run_planner(retrieval_snippets, state_snapshot, query)
    serializable_plan = plan.model_dump() if hasattr(plan, "model_dump") else plan

    output = {
        "user_query": query,
        "use_remote_model": use_remote,
        "remote_result": remote_result,
        "plan": serializable_plan,
    }
    out_path = ROOT / "reports" / "smoke_remote_planner.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
