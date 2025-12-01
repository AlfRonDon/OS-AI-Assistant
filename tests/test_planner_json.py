import json
from pathlib import Path

import pytest

from planner.runner import run_planner
from mock_os import state

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None


def _schema():
    path = Path(__file__).resolve().parents[1] / "contracts" / "planner_output.schema.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _validate(payload):
    schema = _schema()
    if jsonschema is not None:
        jsonschema.Draft7Validator(schema).validate(payload)
    else:
        assert set(schema["required"]).issubset(payload.keys())
        assert isinstance(payload["steps"], list) and payload["steps"]
        for step in payload["steps"]:
            for key in ("step_label", "api_call", "args", "expected_state"):
                assert key in step


@pytest.mark.parametrize(
    "query",
    [
        "open assistant window",
        "update clipboard buffer",
        "persist my intent",
        "log a reminder",
        "adjust a setting",
    ],
)
def test_planner_outputs_valid_json(query):
    snippets = ["mock snippet"]
    plan = run_planner(snippets, state.snapshot(), query)
    payload = plan.model_dump()
    _validate(payload)
    assert payload["intent"] == query
    assert payload["steps"]
