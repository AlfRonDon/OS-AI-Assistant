import copy
from typing import Dict, Any, List

from planner.schema import Plan, Step
from mock_os import state
from telemetry.logger import log_event


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
    preview = {
        "original_state": original,
        "predicted_state": simulated,
        "diff": _diff_states(original, simulated),
        "steps": [s.step_label for s in plan.steps],
    }
    try:
        log_event({"event": "dry_run", "dry_run_diff": preview["diff"]})
    except Exception:
        pass
    return preview


def run(plan: Plan) -> Dict[str, Any]:
    before = state.snapshot()
    state.save_checkpoint()
    previous_expected: Dict[str, Any] | None = None
    applied_steps: List[str] = []
    for step in plan.steps:
        if previous_expected is not None and not state.validate(previous_expected):
            response = _state_mismatch_response(previous_expected)
            try:
                log_event({"event": "run", "run_result": response})
            except Exception:
                pass
            return response
        _apply_step(state.STATE, step)
        applied_steps.append(step.step_label)
        previous_expected = step.expected_state or {}

    if previous_expected is not None and not state.validate(previous_expected):
        response = _state_mismatch_response(previous_expected)
        try:
            log_event({"event": "run", "run_result": response})
        except Exception:
            pass
        return response

    current = state.snapshot()
    result = {
        "applied": True,
        "state": current,
        "applied_steps": applied_steps,
        "diff": _diff_states(before, current),
    }
    try:
        log_event({"event": "run", "run_result": result})
    except Exception:
        pass
    return result


def undo() -> Dict[str, Any]:
    restored = state.restore_last()
    result = {"state": restored}
    try:
        log_event({"event": "undo", "undo_result": result})
    except Exception:
        pass
    return result
