import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from planner.runner import run_planner  # noqa: E402
from retrieval.index import build_index, query_index  # noqa: E402
from mock_os import state  # noqa: E402

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None


PROMPTS_PATH = ROOT / "tests" / "obedience_prompts.json"
REPORT_PATH = ROOT / "reports" / "obedience_report.json"
SCHEMA_PATH = ROOT / "contracts" / "planner_output.schema.json"
TEMPERATURE = 0.0


def _load_prompts(path: Path) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        prompts = json.load(f)
    if not isinstance(prompts, list):
        raise ValueError("prompts file must contain a list")
    return [str(p) for p in prompts][:50]


def _load_schema() -> Dict[str, Any]:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _plan_to_dict(plan_obj: Any) -> Dict[str, Any]:
    if hasattr(plan_obj, "model_dump"):
        return plan_obj.model_dump()
    if isinstance(plan_obj, dict):
        return dict(plan_obj)
    return {
        "intent": getattr(plan_obj, "intent", ""),
        "slots": {},
        "steps": [],
        "sources": [],
        "confidence": 0.0,
        "error": "UNSERIALIZABLE",
    }


def _validate_plan(plan: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, List[str], int]:
    errors: List[str] = []
    extra_fields = 0
    allowed_root = set(schema.get("properties", {}).keys())
    unexpected_root = set(plan.keys()) - allowed_root
    extra_fields += len(unexpected_root)

    if jsonschema is not None:
        validator = jsonschema.Draft7Validator(schema)
        for error in validator.iter_errors(plan):
            errors.append(error.message)
    else:
        required = schema.get("required", [])
        for key in required:
            if key not in plan:
                errors.append(f"missing required field: {key}")
        if not isinstance(plan.get("steps", []), list) or not plan.get("steps"):
            errors.append("steps must be non-empty list")
    return len(errors) == 0, errors, extra_fields


def _ensure_report_dir() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    prompts = _load_prompts(PROMPTS_PATH)
    schema = _load_schema()
    index, docs = build_index()

    results: List[Dict[str, Any]] = []
    valid_count = 0
    extra_field_count = 0
    confidence_total = 0.0
    metadata = {
        "temperature": TEMPERATURE,
        "schema_path": str(SCHEMA_PATH),
        "prompts_path": str(PROMPTS_PATH),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    for prompt in prompts:
        snippets = [s for _, s in query_index(index, docs, prompt, top_k=1)]
        try:
            plan = _plan_to_dict(run_planner(snippets, state.snapshot(), prompt))
        except Exception as exc:  # pragma: no cover - catastrophic path
            plan = {"intent": prompt, "steps": [], "sources": snippets, "confidence": 0.0, "error": str(exc)}
        valid, errors, extras = _validate_plan(plan, schema)
        valid_count += 1 if valid else 0
        extra_field_count += extras
        confidence_total += float(plan.get("confidence", 0.0) or 0.0)
        results.append(
            {
                "prompt_index": len(results),
                "prompt": prompt,
                "valid": valid,
                "confidence": float(plan.get("confidence", 0.0) or 0.0),
                "errors": errors,
                "extra_fields": extras,
            }
        )

    total = len(prompts)
    valid_rate = valid_count / total if total else 0.0
    avg_confidence = confidence_total / total if total else 0.0

    report = {
        "total": total,
        "valid_count": valid_count,
        "valid_rate": valid_rate,
        "extra_field_count": extra_field_count,
        "avg_confidence": avg_confidence,
        "metadata": metadata,
        "per_prompt": results,
    }

    _ensure_report_dir()
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    if valid_rate < 0.85:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
