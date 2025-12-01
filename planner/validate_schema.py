from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Tuple

from jsonschema import Draft7Validator, ValidationError


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["plan_id", "steps", "metadata"],
    "additionalProperties": False,
    "properties": {
        "plan_id": {"type": "string", "minLength": 1},
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/definitions/step"},
        },
        "metadata": {"type": "object", "default": {}},
    },
    "definitions": {
        "expectation": {"type": "object"},
        "retry_policy": {
            "oneOf": [
                {"type": "integer", "minimum": 0},
                {
                    "type": "object",
                    "required": ["limit"],
                    "additionalProperties": False,
                    "properties": {
                        "limit": {"type": "integer", "minimum": 0},
                        "backoff": {"type": "string"},
                        "predicate": {"type": "string"},
                    },
                },
            ]
        },
        "step": {
            "type": "object",
            "required": ["op", "args", "expect"],
            "additionalProperties": False,
            "properties": {
                "op": {
                    "type": "string",
                    "enum": ["read", "write", "patch_json", "run_script"],
                },
                "args": {"type": "object"},
                "expect": {"$ref": "#/definitions/expectation"},
                "id": {"type": "string"},
                "description": {"type": "string"},
                "retry": {"$ref": "#/definitions/retry_policy"},
                "on_fail": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/step"},
                    "default": [],
                },
                "safe_write": {"type": "boolean"},
                "produces": {"type": "array", "items": {"type": "string"}},
                "requires": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}

_VALIDATOR = Draft7Validator(PLAN_SCHEMA)


def load_plan(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"failed to parse JSON from {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"plan at {path} must be a JSON object")
    return parsed


def validate_plan(plan: dict[str, Any]) -> None:
    _VALIDATOR.validate(plan)


def iter_validation_errors(plan: dict[str, Any]) -> Iterable[ValidationError]:
    return _VALIDATOR.iter_errors(plan)


def _validate_path(path: Path) -> Tuple[bool, str]:
    try:
        plan = load_plan(path)
        validate_plan(plan)
        return True, json.dumps(plan, indent=2)
    except Exception as exc:  # pragma: no cover - thin CLI wrapper
        return False, str(exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate planner JSON plans.")
    parser.add_argument("input", nargs="+", help="Path(s) to plan JSON files.")
    parser.add_argument(
        "--dump-schema", action="store_true", help="Print the plan JSON schema and exit."
    )
    args = parser.parse_args(argv)

    if args.dump_schema:
        print(json.dumps(PLAN_SCHEMA, indent=2))
        return 0

    overall_ok = True
    multiple_inputs = len(args.input) > 1
    for candidate in args.input:
        path = Path(candidate)
        ok, message = _validate_path(path)
        if ok:
            if multiple_inputs:
                print(f"{path}: OK")
            else:
                print(message)
        else:
            overall_ok = False
            print(f"{path}: FAIL {message}", flush=True)
    return 0 if overall_ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
