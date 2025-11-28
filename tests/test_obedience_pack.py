import json
import subprocess
import sys
from pathlib import Path


def test_obedience_pack_runs():
    repo_root = Path(__file__).resolve().parents[1]
    report_path = repo_root / "reports" / "obedience_report.json"
    if report_path.exists():
        report_path.unlink()

    script = repo_root / "scripts" / "run_obedience_pack.py"
    result = subprocess.run([sys.executable, str(script)], cwd=repo_root, capture_output=True, text=True)
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"

    assert report_path.exists()
    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("valid_rate", 0) >= 0.85
