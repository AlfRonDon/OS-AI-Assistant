import copy
from typing import Dict, Any, List

from planner.schema import Plan, Step
from mock_os import state


def _apply_step(target_state: Dict[str, Any], step: Step) -> None:
    api = step.api_call
    args = step.args or {}
    target_state.setdefault("windows", [])
    target_state.setdefault("settings", {})
    target_state.setdefault("logs", [])
    target_state.setdefault("clipboard", "")

    if api == "append_log":
        target_state["logs"].append(args.get("message", ""))
    elif api == "open_window":
        window = args.get("window") or {
            "id": f"win-{len(target_state['windows'])+1}",
            "title": args.get("title", "Window"),
            "active": True,
        }
        target_state["windows"].append(window)
    elif api == "write_clipboard":
        target_state["clipboard"] = args.get("text", "")
    elif api == "update_setting":
        key = args.get("key", "unknown")
        target_state["settings"][key] = args.get("value")


def _diff_states(original: Dict[str, Any], updated: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    diff: Dict[str, Dict[str, Any]] = {}
    keys = set(original.keys()) | set(updated.keys())
    for key in keys:
        if original.get(key) != updated.get(key):
            diff[key] = {"from": copy.deepcopy(original.get(key)), "to": copy.deepcopy(updated.get(key))}
    return diff


def _state_mismatch_response(expected_state: Dict[str, Any]) -> Dict[str, Any]:
    current_state = state.snapshot()
    state.restore_last()
    return {
        "applied": False,
        "reason": "STATE_MISMATCH",
        "expected": expected_state,
        "current": current_state,
    }


def dry_run(plan: Plan) -> Dict[str, Any]:
    original = state.snapshot()
    simulated = state.snapshot()
    for step in plan.steps:
        _apply_step(simulated, step)
    return {
        "original_state": original,
        "predicted_state": simulated,
        "diff": _diff_states(original, simulated),
        "steps": [s.step_label for s in plan.steps],
    }


def run(plan: Plan) -> Dict[str, Any]:
    before = state.snapshot()
    state.save_checkpoint()
    previous_expected: Dict[str, Any] | None = None
    applied_steps: List[str] = []
    for step in plan.steps:
        if previous_expected is not None and not state.validate(previous_expected):
            return _state_mismatch_response(previous_expected)
        _apply_step(state.STATE, step)
        applied_steps.append(step.step_label)
        previous_expected = step.expected_state or {}

    if previous_expected is not None and not state.validate(previous_expected):
        return _state_mismatch_response(previous_expected)

    current = state.snapshot()
    return {
        "applied": True,
        "state": current,
        "applied_steps": applied_steps,
        "diff": _diff_states(before, current),
    }


def undo() -> Dict[str, Any]:
    restored = state.restore_last()
    return {"state": restored}
