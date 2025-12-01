import os
import shutil
import subprocess
from pathlib import Path

import pytest


def test_quantize_script_handles_missing_model():
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "quantize_and_validate.sh"
    candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        shutil.which("bash"),
        shutil.which("sh"),
    ]
    shell = next((c for c in candidates if c and Path(c).exists()), None)
    if not shell:
        pytest.skip("No usable shell available to run quantize script")
    shell_lower = shell.lower()
    if "system32" in shell_lower and "bash.exe" in shell_lower:
        pytest.skip("System bash not suitable for running quantize script on Windows")
    probe = subprocess.run([shell, "-c", "echo shell_ok"], capture_output=True, text=True)
    if probe.returncode != 0:
        pytest.skip("Shell is not operational in this environment")
    report_path = repo_root / "reports" / "quantize_validation.json"
    if report_path.exists():
        report_path.unlink()

    env = os.environ.copy()
    env.pop("GPT_OSS_MODEL_PATH", None)
    result = subprocess.run([shell, str(script)], cwd=repo_root, env=env, capture_output=True, text=True)
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert report_path.exists()
