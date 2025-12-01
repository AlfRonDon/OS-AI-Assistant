from __future__ import annotations

import time
from pathlib import Path

import pytest
from jsonschema import ValidationError

from planner import validate_schema
from planner.plan_runner import run_plan

SCENARIO_DIR = Path(__file__).parent
VALID_CASE_PATHS = [
    SCENARIO_DIR / "case1.json",
    SCENARIO_DIR / "case2.json",
    SCENARIO_DIR / "case3.json",
    SCENARIO_DIR / "case4.json",
    SCENARIO_DIR / "case5.json",
    SCENARIO_DIR / "case6.json",
    SCENARIO_DIR / "case7.json",
    SCENARIO_DIR / "case8.json",
    SCENARIO_DIR / "case10.json",
]
INVALID_CASE_PATH = SCENARIO_DIR / "case9.json"


@pytest.fixture(scope="session", autouse=True)
def planner_report() -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = Path("reports") / f"planner-test-{ts}.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("planner tests started\n", encoding="utf-8")
    yield path
    path.write_text(path.read_text(encoding="utf-8") + "planner tests completed\n", encoding="utf-8")


@pytest.fixture(scope="session")
def log_line_writer(planner_report: Path):
    def _write(message: str) -> None:
        with planner_report.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")

    return _write


def test_schema_accepts_valid_cases(log_line_writer) -> None:
    for path in VALID_CASE_PATHS:
        plan = validate_schema.load_plan(path)
        validate_schema.validate_plan(plan)
        log_line_writer(f"validated {path.name}")


def test_schema_rejects_invalid_case() -> None:
    plan = validate_schema.load_plan(INVALID_CASE_PATH)
    with pytest.raises(ValidationError):
        validate_schema.validate_plan(plan)


def test_plan_runner_returns_plan_json() -> None:
    path = SCENARIO_DIR / "case1.json"
    plan = run_plan(path, dry_run=True)
    assert isinstance(plan, dict)
    assert plan["plan_id"] == "case1-summarize-file"
    assert plan["steps"][0]["op"] == "read"


def test_compensating_steps_present() -> None:
    plan = validate_schema.load_plan(SCENARIO_DIR / "case5.json")
    write_steps = [step for step in plan["steps"] if step["op"] == "write"]
    assert any(step.get("on_fail") for step in write_steps), "expected a compensating step on failure"
    compensating = [s for step in write_steps for s in step.get("on_fail", [])]
    assert any(sub.get("op") == "write" for sub in compensating)


def test_retry_policy_on_transient_error() -> None:
    plan = validate_schema.load_plan(SCENARIO_DIR / "case6.json")
    step = plan["steps"][0]
    retry = step.get("retry")
    assert retry and retry.get("limit") == 3


def test_safe_write_flag_present() -> None:
    plan = validate_schema.load_plan(SCENARIO_DIR / "case7.json")
    step = plan["steps"][0]
    assert step.get("safe_write") is True
    assert step["expect"]["mode"] == "safe"


def test_patch_json_expectations() -> None:
    plan = validate_schema.load_plan(SCENARIO_DIR / "case8.json")
    step = plan["steps"][0]
    assert step["op"] == "patch_json"
    patch_ops = step["args"]["patch"]
    assert any(op["op"] == "replace" for op in patch_ops)
    assert "/theme" in step["expect"]["modified_paths"]


def test_permission_denied_simulation() -> None:
    plan = validate_schema.load_plan(SCENARIO_DIR / "case10.json")
    expect = plan["steps"][0]["expect"]
    assert plan["metadata"].get("simulate_permission_denied") is True
    assert expect.get("status") == "permission_denied"


def test_create_missing_file_declares_creation() -> None:
    plan = validate_schema.load_plan(SCENARIO_DIR / "case4.json")
    expect = plan["steps"][0]["expect"]
    assert expect.get("exists") is True
    assert expect.get("status") == "created"


def test_run_script_has_exit_code() -> None:
    plan = validate_schema.load_plan(SCENARIO_DIR / "case3.json")
    expect = plan["steps"][0]["expect"]
    assert expect["exit_code"] == 0
    assert expect["status"] == "ok"
