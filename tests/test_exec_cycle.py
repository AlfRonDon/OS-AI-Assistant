from planner.runner import run_planner
from retrieval.index import build_index, query_index
from mock_os import state
from mock_os.executor import dry_run, run, undo


def test_full_execution_cycle():
    index, docs = build_index()
    snippets = [s for _, s in query_index(index, docs, "clipboard", top_k=2)]
    initial_state = state.snapshot()

    plan = run_planner(snippets, initial_state, "update clipboard buffer")
    preview = dry_run(plan)

    assert preview["original_state"] == initial_state
    assert preview["predicted_state"] != initial_state

    run_result = run(plan)
    after_run = run_result["state"]
    assert after_run != initial_state
    assert state.snapshot() == after_run

    undo_result = undo()
    assert undo_result["state"] == initial_state
    assert state.snapshot() == initial_state
