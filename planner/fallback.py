import copy
import json
from typing import Any, Dict, List


def _steps_from_snippet(snippet: str) -> List[Dict[str, Any]]:
    try:
        parsed = json.loads(snippet)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, dict):
        return []
    snippet_steps = parsed.get("steps")
    if not isinstance(snippet_steps, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for idx, step in enumerate(snippet_steps):
        if not isinstance(step, dict):
            continue
        normalized.append(
            {
                "step_label": step.get("step_label", f"fallback_step_{idx+1}"),
                "api_call": step.get("api_call", "append_log"),
                "args": step.get("args", {}),
                "expected_state": step.get("expected_state", {}),
            }
        )
    return normalized


def fallback_plan(retrieval_snippets: List[str], state_snapshot: Dict[str, Any], user_query: str) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    top_snippet = retrieval_snippets[0] if retrieval_snippets else ""
    snippet_steps = _steps_from_snippet(top_snippet) if top_snippet else []
    if snippet_steps:
        steps.extend(snippet_steps)

    if not steps:
        logs = copy.deepcopy(state_snapshot.get("logs", []))
        steps.append(
            {
                "step_label": "log_fallback_intent",
                "api_call": "append_log",
                "args": {"message": user_query},
                "expected_state": {"logs": logs + [user_query]},
            }
        )

    return {
        "intent": user_query,
        "slots": {},
        "steps": steps,
        "sources": retrieval_snippets,
        "confidence": 0.4,
    }
