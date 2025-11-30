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
_LOG_PATH = Path(__file__).resolve().parents[1] / "reports" / "remote_adapter.log"
_SCHEMA_CACHE: Dict[str, Any] | None = None


def _ensure_logger() -> None:
    if logger.handlers:
        return
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


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
    if jsonschema is None:
        raise RuntimeError("jsonschema is required to validate remote planner output")
    jsonschema.Draft7Validator(schema).validate(payload)


def _mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}***{value[-2:]}"


def _safe_json(obj: Any, limit: int = 4000) -> str:
    try:
        text = json.dumps(obj, ensure_ascii=False)
    except Exception:
        text = str(obj)
    if len(text) > limit:
        return f"{text[:limit]}...(truncated)"
    return text


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


def _masked_headers(headers: Dict[str, str]) -> Dict[str, str]:
    masked = {}
    for key, value in headers.items():
        if "authorization" in key.lower():
            token = value.split("Bearer")[-1].strip() if "Bearer" in value else value
            masked[key] = f"Bearer {_mask_secret(token)}"
        else:
            masked[key] = value
    return masked


def _common_messages(retrieval_snippets: List[Any], state_snapshot: Dict[str, Any], user_query: str) -> Dict[str, Any]:
    payload = {
        "user_query": user_query,
        "retrieval_snippets": retrieval_snippets,
        "state_snapshot": state_snapshot,
    }
    system_text = (
        "You are a deterministic planning engine. "
        "Return only a single JSON object that matches the PlannerOutput schema in contracts/planner_output.schema.json. "
        "Do not include any text outside the JSON object and do not invent additional fields."
    )
    return {"system_text": system_text, "user_payload": payload}


def _call_openai(
    retrieval_snippets: List[Any], state_snapshot: Dict[str, Any], user_query: str, timeout_seconds: int
) -> Dict[str, Any]:
    prompts = _common_messages(retrieval_snippets, state_snapshot, user_query)
    parameters_schema = _function_parameters_schema()
    model = os.getenv("REMOTE_OPENAI_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1"))
    base_url = os.getenv("OPENAI_BASE_URL", os.getenv("REMOTE_OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    url = f"{base_url}/chat/completions"

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

    headers = _openai_headers()
    logger.info(
        "remote adapter request provider=openai model=%s url=%s headers=%s payload=%s",
        model,
        url,
        _masked_headers(headers),
        _safe_json({"messages": messages, "model": model, "tools": payload["tools"], "response_format": payload["response_format"]}),
    )
    response = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
    logger.info("remote adapter response provider=openai status=%s body=%s", response.status_code, _safe_json(response.text))
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("no choices returned from OpenAI")
    message = choices[0].get("message", {})
    parsed: Dict[str, Any] | None = None

    content = message.get("content", "")
    parsed = _parse_json_fragment(content) if content else None

    if parsed is None:
        function_call = message.get("function_call") or {}
        arguments = function_call.get("arguments")
        tool_calls = message.get("tool_calls") or []
        if arguments:
            parsed = _parse_json_fragment(arguments)
        elif tool_calls:
            first_call = tool_calls[0].get("function", {}) if tool_calls else {}
            parsed = _parse_json_fragment(first_call.get("arguments", ""))

    if parsed is None:
        raise RuntimeError("unable to parse JSON from OpenAI response")
    return parsed


def _call_google(
    retrieval_snippets: List[Any], state_snapshot: Dict[str, Any], user_query: str, timeout_seconds: int
) -> Dict[str, Any]:
    prompts = _common_messages(retrieval_snippets, state_snapshot, user_query)
    parameters_schema = _function_parameters_schema()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is required for REMOTE_PROVIDER=google")
    model = os.getenv("REMOTE_GOOGLE_MODEL", os.getenv("GOOGLE_MODEL", "gemini-1.5-pro-latest"))
    base_url = os.getenv("GOOGLE_API_BASE", "https://generativelanguage.googleapis.com")
    url = f"{base_url.rstrip('/')}/v1beta/models/{model}:generateContent?key={api_key}"
    masked_url = url.replace(api_key, _mask_secret(api_key))

    payload = {
        "systemInstruction": {"parts": [{"text": prompts["system_text"]}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(prompts["user_payload"], ensure_ascii=False)}]}],
        "tools": [{"functionDeclarations": [{"name": "emit_plan", "description": "Emit planner output", "parameters": parameters_schema}]}],
        "toolConfig": {"functionCallConfig": {"mode": "ANY", "allowedFunctionNames": ["emit_plan"]}},
        "generationConfig": {"temperature": 0},
    }

    logger.info("remote adapter request provider=google model=%s url=%s payload=%s", model, masked_url, _safe_json(payload))
    response = requests.post(url, json=payload, timeout=timeout_seconds)
    logger.info("remote adapter response provider=google status=%s body=%s", response.status_code, _safe_json(response.text))
    response.raise_for_status()
    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("no candidates returned from Google")

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
    retrieval_snippets: List[Any],
    state_snapshot: Dict[str, Any],
    user_query: str,
    timeout: int = 10,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Invoke a remote planner provider (OpenAI or Google) and return a PlannerOutput-compatible dict.
    Validation against the PlannerOutput schema is enforced before returning the payload.
    """
    _ensure_logger()
    timeout_seconds = int(kwargs.pop("timeout_seconds", timeout) or timeout)
    provider = (os.getenv("REMOTE_PROVIDER", "openai") or "openai").strip().lower()
    try:
        if provider == "openai":
            plan = _call_openai(retrieval_snippets, state_snapshot, user_query, timeout_seconds)
        elif provider == "google":
            plan = _call_google(retrieval_snippets, state_snapshot, user_query, timeout_seconds)
        else:
            raise ValueError(f"unsupported REMOTE_PROVIDER '{provider}'")

        _validate_plan(plan)
        logger.info(
            "remote adapter validated provider=%s confidence=%s steps=%s",
            provider,
            plan.get("confidence"),
            len(plan.get("steps", [])) if isinstance(plan.get("steps"), list) else 0,
        )
        return plan
    except Exception as exc:
        logger.exception("remote planner failed for provider %s", provider)
        raise RuntimeError(f"Remote planner failed for provider '{provider}': {exc}") from exc


def minimal_sanity_check(planner_output: Dict[str, Any]) -> bool:
    try:
        _validate_plan(planner_output)
        return True
    except Exception:
        return False
