import json, os, re, subprocess, time
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "e2e" / "cases"
SANDBOX = ROOT.parents[1] / "sandbox"
REPORTS = ROOT.parents[1] / "reports"


def cmd_run(cmd):
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    return p.returncode, p.stdout + p.stderr


@pytest.fixture(autouse=True)
def ensure_dirs(tmp_path):
    REPORTS.mkdir(parents=True, exist_ok=True)
    SANDBOX.mkdir(parents=True, exist_ok=True)
    # create a default input.json
    (SANDBOX / "input.json").write_text(json.dumps({"orig":1}), encoding="utf-8")
    yield
    # cleanup minimal (keep reports)


def load_case(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def assert_master_done(output):
    assert re.search(r"MASTER_DONE id=[0-9a-fA-F-]+ rc=0 out=", output), output


def test_all_cases_dry_run():
    for f in sorted(CASES_DIR.glob('case*.json')):
        case = load_case(f)
        rc, out = cmd_run(f'python pipeline_runner.py --task {f} --dry-run')
        assert rc == 0, out
        assert_master_done(out)


def test_exec_cases_expectations():
    # run through cases that require actual exec or check expectations
    for f in sorted(CASES_DIR.glob('case*.json')):
        case = load_case(f)
        allow_exec = case.get('meta', {}).get('simulate_transient', False) or case.get('meta', {}).get('simulate_concurrent', False) or case['task_id'].endswith('create-and-run-script') or case.get('meta', {}).get('force_corrupt_plan', False)
        # run actual execution only when not permission-denied simulation
        if case.get('meta', {}).get('should_fail', False):
            # expect failure rc != 0
            rc, out = cmd_run(f'python pipeline_runner.py --task {f} --allow-exec')
            assert rc != 0
            continue
        # otherwise run with allow-exec to actually modify sandbox
        rc, out = cmd_run(f'python pipeline_runner.py --task {f} {"--allow-exec" if allow_exec else ""}')
        assert rc == 0, out
        assert_master_done(out)
