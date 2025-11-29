import json
import subprocess
import sys
from pathlib import Path


def test_obedience_pack_runs():
    repo_root = Path(__file__).resolve().parents[1]
    report_path = repo_root / "reports" / "obedience_report.json"
    prompts_path = repo_root / "tests" / "obedience_prompts.json"
    if report_path.exists():
        report_path.unlink()

    script = repo_root / "scripts" / "run_obedience_pack.py"
    result = subprocess.run([sys.executable, str(script)], cwd=repo_root, capture_output=True, text=True)
    assert result.returncode in {0, 2}, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert report_path.exists(), "report file not created"

    with open(prompts_path, "r", encoding="utf-8") as f:
        expected_prompts = json.load(f)
    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total = data.get("total")
    valid_rate = data.get("valid_rate", 0.0)
    per_prompt = data.get("per_prompt", [])
    metadata = data.get("metadata", {})

    assert total == len(expected_prompts), "report total does not match prompts count"
    assert len(per_prompt) == len(expected_prompts), "per_prompt length mismatch"
    assert metadata.get("prompts_path"), "metadata missing prompts_path"
    assert metadata.get("schema_path"), "metadata missing schema_path"
    for idx, entry in enumerate(per_prompt):
        assert entry.get("prompt_index") == idx
        assert entry.get("prompt") == expected_prompts[idx]
        assert "valid" in entry

    if valid_rate < 0.85:
        assert result.returncode == 2, "runner should exit 2 when valid_rate is low"
    else:
        assert result.returncode == 0, "runner should exit 0 when valid_rate is sufficient"
