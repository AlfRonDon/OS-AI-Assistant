from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

import requests

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None  # type: ignore

logger = logging.getLogger(__name__)

_SCHEMA_CACHE: Dict[str, Any] | None = None


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[1] / "contracts" / "planner_output.schema.json"


def _planner_schema() -> Dict[str, Any]:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = json.loads(_schema_path().read_text(encoding="utf-8"))
    return _SCHEMA_CACHE


def _function_parameters_schema() -> Dict[str, Any]:
    schema = _planner_schema()
    return {
        "type": "object",
        "properties": schema.get("properties", {}),
        "required": schema.get("required", []),
        "additionalProperties": schema.get("additionalProperties", False),
    }


def _validate_plan(payload: Dict[str, Any]) -> None:
    schema = _planner_schema()
    if jsonschema is not None:
        jsonschema.Draft7Validator(schema).validate(payload)
        return

    required = schema.get("required", [])
    for key in required:
        if key not in payload:
            raise ValueError(f"missing required field: {key}")

    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list")
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("step entries must be objects")
        for field in ("step_label", "api_call", "args", "expected_state"):
            if field not in step:
                raise ValueError(f"step missing {field}")


def _error_response(user_query: str, reason: str) -> Dict[str, Any]:
    return {
        "intent": user_query,
        "slots": {},
        "steps": [],
        "sources": [],
        "confidence": 0.0,
        "error": reason,
    }


def _parse_json_fragment(text: str) -> Dict[str, Any] | None:
    stripped = (text or "").strip()
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


def _common_messages(retrieval_snippets: List[Any], state_snapshot: Dict[str, Any], user_query: str) -> Dict[str, Any]:
    payload = {
        "user_query": user_query,
        "retrieval_snippets": retrieval_snippets,
        "state_snapshot": state_snapshot,
    }
    system_text = (
        "You are a deterministic planning engine. "
        "Use the emit_plan function to return a JSON payload that matches the PlannerOutput schema. "
        "Do not return text outside the JSON and avoid extra keys."
    )
    return {"system_text": system_text, "user_payload": payload}


def _openai_headers() -> Dict[str, str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for REMOTE_PROVIDER=openai")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    org = os.getenv("OPENAI_ORG")
    project = os.getenv("OPENAI_PROJECT")
    if org:
        headers["OpenAI-Organization"] = org
    if project:
        headers["OpenAI-Project"] = project
    return headers


def _call_openai(
    retrieval_snippets: List[Any], state_snapshot: Dict[str, Any], user_query: str, timeout_seconds: int
) -> Dict[str, Any]:
    model = os.getenv("REMOTE_OPENAI_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1"))
    base_url = os.getenv("OPENAI_BASE_URL", os.getenv("REMOTE_OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    url = f"{base_url}/chat/completions"

    prompts = _common_messages(retrieval_snippets, state_snapshot, user_query)
    parameters_schema = _function_parameters_schema()
    messages = [
        {"role": "system", "content": prompts["system_text"]},
        {"role": "user", "content": json.dumps(prompts["user_payload"], ensure_ascii=False)},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "emit_plan",
                    "description": "Return the planner output. Follow the parameters schema exactly.",
                    "parameters": parameters_schema,
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "emit_plan"}},
        "response_format": {"type": "json_object"},
    }

    response = requests.post(url, headers=_openai_headers(), json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("no choices returned")
    message = choices[0].get("message", {})
    parsed: Dict[str, Any] | None = None

    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        arguments = tool_calls[0].get("function", {}).get("arguments", "")
        parsed = _parse_json_fragment(arguments)
    if parsed is None:
        parsed = _parse_json_fragment(message.get("content", ""))

    if parsed is None:
        raise RuntimeError("unable to parse JSON from OpenAI response")
    return parsed


def _call_google(
    retrieval_snippets: List[Any], state_snapshot: Dict[str, Any], user_query: str, timeout_seconds: int
) -> Dict[str, Any]:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is required for REMOTE_PROVIDER=google")
    model = os.getenv("REMOTE_GOOGLE_MODEL", os.getenv("GOOGLE_MODEL", "gemini-1.5-pro-latest"))
    base_url = os.getenv("GOOGLE_API_BASE", "https://generativelanguage.googleapis.com")
    url = f"{base_url.rstrip('/')}/v1beta/models/{model}:generateContent?key={api_key}"

    prompts = _common_messages(retrieval_snippets, state_snapshot, user_query)
    parameters_schema = _function_parameters_schema()
    payload = {
        "systemInstruction": {"parts": [{"text": prompts["system_text"]}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(prompts["user_payload"], ensure_ascii=False)}]}],
        "tools": [{"functionDeclarations": [{"name": "emit_plan", "description": "Emit planner output", "parameters": parameters_schema}]}],
        "toolConfig": {"functionCallConfig": {"mode": "ANY", "allowedFunctionNames": ["emit_plan"]}},
        "generationConfig": {"temperature": 0},
    }

    response = requests.post(url, json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("no candidates returned")

    candidate = candidates[0]
    content = candidate.get("content") or candidate
    parts = content.get("parts") or []
    parsed: Dict[str, Any] | None = None
    for part in parts:
        if not isinstance(part, dict):
            continue
        if "functionCall" in part:
            args = part["functionCall"].get("args")
            if isinstance(args, dict):
                parsed = args
            elif isinstance(args, str):
                parsed = _parse_json_fragment(args)
            break
        if "text" in part:
            parsed = _parse_json_fragment(part["text"])
            if parsed:
                break
    if parsed is None:
        raise RuntimeError("unable to parse JSON from Google response")
    return parsed


def call_remote_planner(
    retrieval_snippets: List[Any], state_snapshot: Dict[str, Any], user_query: str, timeout_seconds: int = 20
) -> Dict[str, Any]:
    """
    Invoke a remote planner provider (OpenAI or Google) and return a PlannerOutput-compatible dict.
    Validation against the PlannerOutput schema is enforced before returning the payload.
    """
    provider = (os.getenv("REMOTE_PROVIDER", "openai") or "openai").strip().lower()
    try:
        if provider == "openai":
            plan = _call_openai(retrieval_snippets, state_snapshot, user_query, timeout_seconds)
        elif provider == "google":
            plan = _call_google(retrieval_snippets, state_snapshot, user_query, timeout_seconds)
        else:
            raise ValueError(f"unsupported REMOTE_PROVIDER '{provider}'")

        _validate_plan(plan)
        return plan
    except Exception as exc:
        logger.error("remote planner failed for provider %s: %s", provider, exc)
        return _error_response(user_query, f"REMOTE_CALL_FAIL: {exc}")


def minimal_sanity_check(planner_output: Dict[str, Any]) -> bool:
    try:
        _validate_plan(planner_output)
        return True
    except Exception:
        return False
