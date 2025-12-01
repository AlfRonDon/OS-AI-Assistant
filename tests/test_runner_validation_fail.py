from planner import runner


def test_runner_returns_validation_fail_and_skips_dry_run(monkeypatch):
    monkeypatch.setattr(runner, "_call_model", lambda prompt: {"intent": "bad"})

    dry_run_calls = {"count": 0}

    def broken_fallback(snippets, state_snapshot, user_query):
        return {"intent": user_query}  # invalid to force validation failure after fallback

    monkeypatch.setattr(runner, "fallback_plan", broken_fallback)

    def fake_dry_run(plan):
        dry_run_calls["count"] += 1
        return {"noop": True}

    monkeypatch.setattr("mock_os.executor.dry_run", fake_dry_run)

    result = runner.run_planner_with_preview([], {}, "bad query")
    assert result["plan"]["error"] == "VALIDATION_FAIL"
    assert result["plan"]["steps"] == []
    assert result["dry_run"] is None
    assert dry_run_calls["count"] == 0
