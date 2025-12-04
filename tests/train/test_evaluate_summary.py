import json
from pathlib import Path

from tools.train import evaluate


def test_evaluate_summary_fields(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    # Minimal valid plan/response for evaluation
    plan = {
        "plan_id": "sample",
        "metadata": {},
        "steps": [{"op": "read", "args": {"path": "sandbox/tmp.json"}, "expect": {}}],
    }
    record = {
        "id": "sample-id",
        "instruction": "sample instruction",
        "plan": plan,
        "executor": {"rc": 0, "stdout": "", "stderr": ""},
        "response": plan,
        "metadata": {},
    }
    dataset_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    rc, eval_json, eval_md, summary = evaluate.evaluate(dataset_path, log_path=None)

    assert rc == 0
    assert eval_json.exists()
    assert eval_md.exists()
    assert summary["dataset"] == dataset_path.as_posix()
    assert "strict_match_rate" in summary
    assert "relaxed_match_rate" in summary
    assert summary["size"] == 1
