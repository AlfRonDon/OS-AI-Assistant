import copy
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from planner.fallback import fallback_plan
from planner.prompt import build_prompt
from planner.schema import Plan

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

try:
    from llama_cpp import Llama  # type: ignore
except ImportError:  # pragma: no cover
    Llama = None  # type: ignore


_LLM = None
logger = logging.getLogger(__name__)


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "contracts" / "planner_output.schema.json"


def _load_schema() -> Dict[str, Any]:
    with open(_schema_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def _validate_with_schema(payload: Dict[str, Any]) -> None:
    schema = _load_schema()
    if jsonschema is not None:
        jsonschema.Draft7Validator(schema).validate(payload)
        return
    required = schema.get("required", [])
    allowed_root = set(schema.get("properties", {}).keys())
    unexpected_root = set(payload.keys()) - allowed_root
    if unexpected_root:
        raise ValueError(f"unexpected fields: {sorted(unexpected_root)}")
    for key in required:
        if key not in payload:
            raise ValueError(f"missing required field: {key}")
    if not isinstance(payload.get("steps", []), list) or not payload["steps"]:
        raise ValueError("steps must be non-empty list")
    for step in payload["steps"]:
        for field in ("step_label", "api_call", "args", "expected_state"):
            if field not in step:
                raise ValueError(f"step missing {field}")
        allowed_step = set(schema["properties"]["steps"]["items"]["properties"].keys())
        unexpected_step = set(step.keys()) - allowed_step
        if unexpected_step:
            raise ValueError(f"unexpected step fields: {sorted(unexpected_step)}")


def _validation_failure_response(user_query: str) -> Dict[str, Any]:
    return {
        "intent": user_query,
        "slots": {},
        "steps": [],
        "sources": [],
        "confidence": 0.0,
        "error": "VALIDATION_FAIL",
    }


def _load_llm():
    global _LLM
    if _LLM is not None or Llama is None:
        return _LLM
    model_path = (
        os.getenv("GPT_OSS_MODEL_PATH")
        or os.getenv("LLAMA_MODEL_PATH")
        or os.path.join("models", "gpt-oss-20b.gguf")
        or "gpt-oss-20b.gguf"
    )
    candidate = Path(model_path)
    if not candidate.exists():
        return None
    try:
        _LLM = Llama(model_path=str(candidate), seed=0)
    except Exception:
        _LLM = None
    return _LLM


def _parse_json(text: str) -> Dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def _call_model(prompt: str) -> Dict[str, Any] | None:
    llm = _load_llm()
    if llm is None:
        return None
    try:
        completion = llm(prompt, max_tokens=512, temperature=0, stop=["\n\n", "\r\n"])
        text = completion.get("choices", [{}])[0].get("text", "")
        return _parse_json(text)
    except Exception:
        return None


def _deterministic_plan(retrieval_snippets: List[str], state_snapshot: Dict[str, Any], user_query: str) -> Dict[str, Any]:
    base_state = copy.deepcopy(state_snapshot)
    windows = base_state.get("windows", [])
    settings = base_state.get("settings", {})
    logs = base_state.get("logs", [])
    steps: List[Dict[str, Any]] = []

    steps.append(
        {
            "step_label": "log_query",
            "api_call": "append_log",
            "args": {"message": user_query},
            "expected_state": {"logs": logs + [user_query]},
        }
    )

    new_window = {"id": f"win-{len(windows)+1}", "title": "Assistant", "active": True}
    steps.append(
        {
            "step_label": "focus_assistant",
            "api_call": "open_window",
            "args": {"window": new_window},
            "expected_state": {"windows": windows + [new_window]},
        }
    )

    if "clipboard" in user_query.lower():
        steps.append(
            {
                "step_label": "set_clipboard",
                "api_call": "write_clipboard",
                "args": {"text": user_query},
                "expected_state": {"clipboard": user_query},
            }
        )
    else:
        updated_settings = copy.deepcopy(settings)
        updated_settings["last_intent"] = user_query
        steps.append(
            {
                "step_label": "persist_intent",
                "api_call": "update_setting",
                "args": {"key": "last_intent", "value": user_query},
                "expected_state": {"settings": updated_settings},
            }
        )

    plan = {
        "intent": user_query,
        "slots": {},
        "steps": steps,
        "sources": retrieval_snippets,
        "confidence": 0.72,
    }
    return plan


def run_planner(retrieval_snippets: List[str], state_snapshot: Dict[str, Any], user_query: str):
    prompt = build_prompt(retrieval_snippets, state_snapshot, user_query)
    model_plan = _call_model(prompt)
    used_fallback = False
    raw_plan: Dict[str, Any] = {}

    if model_plan is None:
        used_fallback = True
        raw_plan = fallback_plan(retrieval_snippets, state_snapshot, user_query)
    else:
        raw_plan = model_plan

    try:
        _validate_with_schema(raw_plan)
    except Exception as exc:
        logger.error("plan validation failed: %s", exc)
        used_fallback = True
        raw_plan = fallback_plan(retrieval_snippets, state_snapshot, user_query)
        try:
            _validate_with_schema(raw_plan)
        except Exception as fallback_exc:
            logger.error("fallback validation failed: %s", fallback_exc)
            return _validation_failure_response(user_query)

    if not used_fallback:
        confidence = float(raw_plan.get("confidence", 0.0) or 0.0)
        if confidence < 0.5:
            logger.warning("low confidence %.3f; using fallback", confidence)
            raw_plan = fallback_plan(retrieval_snippets, state_snapshot, user_query)
            try:
                _validate_with_schema(raw_plan)
            except Exception as exc:
                logger.error("fallback validation failed: %s", exc)
                return _validation_failure_response(user_query)

    return Plan.model_validate(raw_plan)


def run_planner_with_preview(
    retrieval_snippets: List[str], state_snapshot: Dict[str, Any], user_query: str
) -> Dict[str, Any]:
    plan = run_planner(retrieval_snippets, state_snapshot, user_query)
    if isinstance(plan, dict) and plan.get("error") == "VALIDATION_FAIL":
        return {"plan": plan, "dry_run": None}

    from mock_os.executor import dry_run  # local import to avoid cycle

    preview = dry_run(plan)
    return {"plan": plan, "dry_run": preview}
