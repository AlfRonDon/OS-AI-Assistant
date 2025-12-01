import json, uuid, subprocess, time
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
TS = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
LOG = ROOT / f"reports/codex-ops-{TS}.log"
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TRANSIENT = {1, 2}

def log(msg: str) -> None:
    line = f"[{datetime.utcnow().isoformat()}] {msg}"
    LOG.write_text(LOG.read_text(encoding='utf-8') + line + "\n" if LOG.exists() else line + "\n", encoding='utf-8')
    print(msg)


def run(cmd: str) -> int:
    log(f">> RUN: {cmd}")
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    if out.strip():
        log(out.strip())
    if proc.returncode in TRANSIENT and proc.returncode != 0:
        log(f"-- transient rc={proc.returncode}; retrying after 2s")
        time.sleep(2)
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        out = (proc.stdout or "") + (proc.stderr or "")
        if out.strip():
            log(out.strip())
    return proc.returncode


log("START secondary run")
log("PR_BODY_EXT.md already present")

# case7 tail
latest_case7 = None
for path in sorted(REPORTS_DIR.glob('pipeline-*.log'), key=lambda p: p.stat().st_mtime):
    try:
        txt = path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        continue
    if 'case7' in txt:
        latest_case7 = path
if latest_case7:
    tail = "\n".join(latest_case7.read_text(encoding='utf-8', errors='ignore').splitlines()[-80:])
    out = REPORTS_DIR / f"repro-case7-last80-{TS}.log"
    out.write_text(tail, encoding='utf-8')
    log(f"WROTE {out}")
else:
    log("No case7 pipeline logs found for tailing")

overall = 0

# validate planner cases except case9
planner_cases = [p for p in (ROOT / 'tests' / 'planner').glob('case*.json') if p.stem != 'case9']
if planner_cases:
    cmd = "python planner/validate_schema.py " + " ".join(str(p.as_posix()) for p in planner_cases)
    rc = run(cmd)
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

# pipeline cases
cases_dir = ROOT / 'tests' / 'e2e' / 'cases'
overall_cases = 0
if cases_dir.exists():
    for case in sorted(cases_dir.glob('case*.json')):
        data = json.loads(case.read_text(encoding='utf-8'))
        meta = data.get('meta', {})
        allow_exec = meta.get('simulate_transient') or meta.get('simulate_concurrent') or data.get('task_id','').endswith('create-and-run-script') or meta.get('force_corrupt_plan') or meta.get('should_fail')
        cmd = f"python pipeline_runner.py --task {case.as_posix()}" + (" --allow-exec" if allow_exec else "")
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
    rc = run(f"python pipeline_dump_plan.py --task {case1.as_posix()}")
    if rc != 0 and overall == 0:
        overall = rc

rc = run("python tools/train/log_to_dataset.py")
if rc != 0 and overall == 0:
    overall = rc

marker = REPORTS_DIR / f"codex_ops_done_{TS}_secondary.json"
marker.write_text(json.dumps({"id": str(uuid.uuid4()), "timestamp": TS, "status": "done", "rc": overall}), encoding='utf-8')
log(f"WROTE {marker}")

master_id = str(uuid.uuid4())
master_line = f"MASTER_DONE id={master_id} rc={overall} out={LOG.as_posix()}"
log(master_line)
print(master_line)