import json, uuid, subprocess, time
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
TS = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
LOG = ROOT / f"reports/codex-ops-{TS}.log"
LOG.parent.mkdir(parents=True, exist_ok=True)
TRANSIENT = {1, 2}

def log(msg: str) -> None:
    line = f"[{datetime.utcnow().isoformat()}] {msg}"
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')
    print(msg)


def run(cmd: str) -> int:
    log(f">> RUN: {cmd}")
    proc = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    out = (proc.stdout or '') + (proc.stderr or '')
    if out.strip():
        log(out.strip())
    if proc.returncode in TRANSIENT and proc.returncode != 0:
        log(f"-- transient rc={proc.returncode}; retrying after 2s")
        time.sleep(2)
        proc = subprocess.run(cmd, shell=True, text=True, capture_output=True)
        out = (proc.stdout or '') + (proc.stderr or '')
        if out.strip():
            log(out.strip())
    return proc.returncode

overall = 0
log("START tertiary run")

planner_cases = [p for p in (ROOT / 'tests' / 'planner').glob('case*.json') if p.stem != 'case9']
if planner_cases:
    files = " ".join(str(p.relative_to(ROOT).as_posix()) for p in planner_cases)
    rc = run(f"python planner/validate_schema.py {files}")
    if rc != 0 and overall == 0:
        overall = rc

rc = run("pytest tests/planner -q")
if rc != 0 and overall == 0:
    overall = rc

fr = ROOT / 'tests' / 'utils' / 'flaky_runner.py'
if fr.exists():
    rc = run("python tests/utils/flaky_runner.py pytest tests/e2e -q")
    if rc != 0 and overall == 0:
        overall = rc

cases_dir = ROOT / 'tests' / 'e2e' / 'cases'
overall_cases = 0
if cases_dir.exists():
    for case in sorted(cases_dir.glob('case*.json')):
        data = json.loads(case.read_text(encoding='utf-8'))
        meta = data.get('meta', {})
        allow_exec = meta.get('simulate_transient') or meta.get('simulate_concurrent') or data.get('task_id','').endswith('create-and-run-script') or meta.get('force_corrupt_plan') or meta.get('should_fail')
        cmd = f"python pipeline_runner.py --task {case.relative_to(ROOT).as_posix()}" + (" --allow-exec" if allow_exec else "")
        rc = run(cmd)
        should_fail = meta.get('should_fail', False)
        if should_fail and rc == 0:
            overall_cases = 1
        if not should_fail and rc != 0:
            overall_cases = rc
    log(f"PIPELINE_CASES_STATUS {overall_cases}")
    if overall_cases != 0 and overall == 0:
        overall = overall_cases

case1 = ROOT / 'tests' / 'e2e' / 'case1.json'
if case1.exists():
    rc = run(f"python pipeline_dump_plan.py --task {case1.relative_to(ROOT).as_posix()}")
    if rc != 0 and overall == 0:
        overall = rc

rc = run("python tools/train/log_to_dataset.py")
if rc != 0 and overall == 0:
    overall = rc

marker = LOG.parent / f"codex_ops_done_{TS}_tertiary.json"
marker.write_text(json.dumps({"id": str(uuid.uuid4()), "timestamp": TS, "status": "done", "rc": overall}), encoding='utf-8')
log(f"WROTE {marker}")
master_id = str(uuid.uuid4())
master_line = f"MASTER_DONE id={master_id} rc={overall} out={LOG.as_posix()}"
log(master_line)
print(master_line)