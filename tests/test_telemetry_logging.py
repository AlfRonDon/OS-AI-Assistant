from pathlib import Path

from mock_os import executor, state
from planner.runner import run_planner
from retrieval.index import build_index, query_index


def test_telemetry_logging_cycle():
    repo_root = Path(__file__).resolve().parents[1]
    log_path = repo_root / "telemetry" / "events.log"
    if log_path.exists():
        log_path.unlink()

    index, docs = build_index()
    snippets = [s for _, s in query_index(index, docs, "clipboard", top_k=1)]
    plan = run_planner(snippets, state.snapshot(), "update clipboard buffer")
    executor.dry_run(plan)
    executor.run(plan)
    executor.undo()

    assert log_path.exists()
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    content = "\n".join(lines)
    assert "retrieval_ids" in content
    assert "planner_output_hash" in content
    assert "dry_run_diff" in content
    assert "run_result" in content
    assert len(lines) >= 4
