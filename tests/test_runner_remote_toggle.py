def test_runner_imports_without_remote_env(monkeypatch):
    monkeypatch.delenv("USE_REMOTE_MODEL", raising=False)

    from planner import runner

    called = {"count": 0}
    if runner.remote_adapter:
        # Assert remote path stays inactive when USE_REMOTE_MODEL is not set.
        def _boom(*_args, **_kwargs):
            called["count"] += 1
            raise AssertionError("remote adapter should not be invoked when USE_REMOTE_MODEL is unset")

        monkeypatch.setattr(runner.remote_adapter, "call_remote_planner", _boom)

    plan = runner.run_planner([], {"windows": [], "settings": {}, "logs": []}, "ping")
    assert plan
    if runner.remote_adapter:
        assert called["count"] == 0
