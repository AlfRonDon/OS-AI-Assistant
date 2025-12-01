from planner import runner
from planner.fallback import fallback_plan


def test_fallback_plan_shape():
    plan = fallback_plan([], {"logs": []}, "hello fallback")
    assert plan["intent"] == "hello fallback"
    assert plan["steps"]
    assert plan["confidence"] == 0.4


def test_runner_uses_fallback_on_validation_failure(monkeypatch):
    monkeypatch.setattr(runner, "_call_model", lambda prompt: {"intent": "invalid"})

    calls = {"count": 0}

    def fake_fallback(snippets, state_snapshot, user_query):
        calls["count"] += 1
        return {
            "intent": user_query,
            "slots": {},
            "steps": [{"step_label": "fb", "api_call": "append_log", "args": {}, "expected_state": {}}],
            "sources": snippets,
            "confidence": 0.4,
        }

    monkeypatch.setattr(runner, "fallback_plan", fake_fallback)

    plan = runner.run_planner(["snippet"], {"logs": []}, "trigger validation fail")
    assert calls["count"] == 1
    assert plan.intent == "trigger validation fail"
    assert plan.steps[0].step_label == "fb"
    assert plan.confidence == 0.4
