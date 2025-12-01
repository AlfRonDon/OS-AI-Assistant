from planner.schema import Plan, Step
from mock_os import executor, state


def test_run_aborts_on_state_mismatch():
    initial = state.snapshot()
    bad_step = Step(
        step_label="write_clipboard",
        api_call="write_clipboard",
        args={"text": "abc"},
        expected_state={"clipboard": "def"},
    )
    plan = Plan(intent="safety", slots={}, steps=[bad_step], sources=[], confidence=0.9)

    result = executor.run(plan)

    assert result["applied"] is False
    assert result["reason"] == "STATE_MISMATCH"
    assert result["expected"] == {"clipboard": "def"}
    assert state.snapshot() == initial
