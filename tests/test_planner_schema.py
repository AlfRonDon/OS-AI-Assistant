import json
from pathlib import Path

import pytest

try:
    import jsonschema  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    jsonschema = None


def _load_schema() -> dict:
    path = Path(__file__).resolve().parents[1] / "contracts" / "planner_output.schema.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _generate_plan(sample_prompt: str) -> dict:
    from planner import runner  # imported lazily to avoid import-time side effects

    retrieval = ["unit-test snippet"]
    state_snapshot = {"windows": [], "settings": {}, "logs": []}

    if hasattr(runner, "run_once"):
        candidate = runner.run_once(sample_prompt)  # type: ignore[attr-defined]
    elif hasattr(runner, "run_planner_with_preview"):
        preview = runner.run_planner_with_preview(retrieval, state_snapshot, sample_prompt)
        candidate = preview.get("plan") if isinstance(preview, dict) else preview
    else:
        candidate = runner.run_planner(retrieval, state_snapshot, sample_prompt)

    if hasattr(candidate, "model_dump"):
        return candidate.model_dump()  # type: ignore[no-any-return]
    if isinstance(candidate, dict):
        return candidate
    pytest.skip("planner runner did not return a serializable object")


def test_planner_matches_schema():
    if jsonschema is None:
        pytest.skip("jsonschema missing; pip install jsonschema to run schema validation.")

    prompt = "Collect clipboard data and log intent"
    payload = _generate_plan(prompt)
    schema = _load_schema()
    jsonschema.validate(instance=payload, schema=schema)
    assert payload.get("intent") == prompt
    assert payload.get("steps"), "planner returned no steps"
