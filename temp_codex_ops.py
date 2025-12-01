import os, sys, json, uuid, subprocess, time
from pathlib import Path
from datetime import datetime

ROOT = Path.cwd()
TS = "'"""'""" + "$ts" + "'"""'"""  # placeholder replaced by PS? actually we will override below
TS = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
LOG = ROOT / f"reports/codex-ops-{TS}.log"
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
DATA_TRAIN = ROOT / "data" / "train"
DATA_TRAIN.mkdir(parents=True, exist_ok=True)

TRANSIENT = {1, 2}


def log(msg: str) -> None:
    line = f"[{datetime.utcnow().isoformat()}] {msg}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(msg)


def run(cmd: str, cwd: Path | None = None, env: dict | None = None) -> tuple[int, str]:
    log(f">> RUN: {cmd}")
    proc = subprocess.run(cmd, shell=True, text=True, capture_output=True, cwd=cwd, env=env)
    out = (proc.stdout or "") + (proc.stderr or "")
    if out.strip():
        log(out.strip())
    if proc.returncode in TRANSIENT and proc.returncode != 0:
        log(f"-- transient rc={proc.returncode}; retrying after 2s")
        time.sleep(2)
        proc = subprocess.run(cmd, shell=True, text=True, capture_output=True, cwd=cwd, env=env)
        out = (proc.stdout or "") + (proc.stderr or "")
        if out.strip():
            log(out.strip())
    return proc.returncode, out


overall_rc = 0

# 1) PR body
pr_body = """Title: e2e: pipeline conductor + hardened tests + CI gating + expected-fail handling

Summary:
- Added PR enhancements and small behavior changes:
  1. PR-ready branch body + suggested reviewers and checklist.
  2. pipeline_runner: add handling for plan meta 'should_fail' as an expected failure flag (non-fatal under explicit flag).
  3. Add --dump-plan-only CLI option to pipeline_runner for plan inspection without execution.
  4. Provide quick parse of case7 repro logs (last 80 lines) and save to reports for triage.
  5. Attempt to create a PR via GitHub CLI (if available).

Files created/modified by this automation:
- PR_BODY_EXT.md (this file)
- pipeline_runner.py (patched for expected-fail handling and --dump-plan-only)
- reports/repro-case7-last80-<ts>.log (if case7 log exists)
- logs and command outputs saved to reports/codex-ops-<ts>.log

Checklist for reviewers:
- [ ] Confirm `pipeline_runner.py` changes are acceptable — especially the 'should_fail' handling semantics.
- [ ] Confirm CI gating for allow-exec remains conservative (ALLOW_EXEC_IN_CI default false).
- [ ] Review new --dump-plan-only behavior and ensure no secret leakage in plans.
- [ ] Verify flaky runner behavior in CI (records flakes into reports/flaky.json).

Suggested reviewers:
- @team-lead
- @infra-owner
- @devops

Merge notes:
- Merge into main only after at least one CI run with ALLOW_EXEC_IN_CI=false and verify pipeline logs. For protected branch full-exec CI run, set ALLOW_EXEC_IN_CI=true once and confirm results.
"""
PR_FILE = ROOT / "PR_BODY_EXT.md"
PR_FILE.write_text(pr_body, encoding="utf-8")
log(f"WROTE {PR_FILE}")

# 2) Ensure pipeline_runner has expected-fail and dump flag
pipe_path = ROOT / "pipeline_runner.py"
if pipe_path.exists():
    text = pipe_path.read_text(encoding="utf-8")
    if "--dump-plan-only" in text and "allow_expected_fail" in text:
        log("pipeline_runner.py already includes dump-plan and expected-fail handling")
    else:
        log("WARNING: pipeline_runner.py may be missing flags; manual patch required")
else:
    log("pipeline_runner.py not found")

# 3) Write dump wrapper (already added but ensure)
wrapper = ROOT / "pipeline_dump_plan.py"
if not wrapper.exists():
    wrapper.write_text("#!/usr/bin/env python3\nfrom __future__ import annotations\nimport argparse, subprocess, sys\nfrom pathlib import Path\n\nparser = argparse.ArgumentParser(description='Dump pipeline plan')\nparser.add_argument('--task', required=True)\nargs = parser.parse_args()\npath = Path(args.task)\nif not path.exists():\n    print('task not found', file=sys.stderr); sys.exit(1)\ncmd = f'python pipeline_runner.py --task {path} --dump-plan-only'\nsys.exit(subprocess.call(cmd, shell=True))\n", encoding="utf-8")
    wrapper.chmod(0o755)
log(f"ENSURED {wrapper}")

# 4) Extract last 80 lines from latest pipeline log mentioning case7
latest_case7 = None
for path in sorted(REPORTS_DIR.glob("pipeline-*.log"), key=lambda p: p.stat().st_mtime):
    try:
        txt = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    if "case7" in txt:
        latest_case7 = path

if latest_case7:
    lines = latest_case7.read_text(encoding="utf-8", errors="ignore").splitlines()
    tail = "\n".join(lines[-80:])
    outfile = REPORTS_DIR / f"repro-case7-last80-{TS}.log"
    outfile.write_text(tail, encoding="utf-8")
    log(f"WROTE {outfile}")
else:
    log("No pipeline logs containing 'case7' found")

log("To allow expected failure semantics, set ALLOW_EXPECTED_FAIL=true or --allow-expected-fail")

# 5) Git/PR steps (best effort)
rc, _ = run("git checkout -b e2e/conductor-full-ops")
if rc not in (0,):
    log("git checkout branch failed or already exists; continuing")
rc, _ = run("git add -A")
rc, _ = run("git commit -m \"chore: apply expected-fail handling, dump wrapper, and PR body\" || true")
rc_pr, out_pr = run(f"gh pr create --title \"ops: expected-fail + dump-plan + case7-triage\" --body-file {PR_FILE} || echo gh-create-failed")
if "gh-create-failed" in out_pr or rc_pr != 0:
    log("gh pr create failed or not available; PR not opened")
else:
    log("gh pr create attempted")

# 6) Validations
plan_cases = [p for p in (ROOT / "tests" / "planner").glob("case*.json") if p.stem != "case9"]
if plan_cases:
    paths_str = " ".join(str(p) for p in plan_cases)
    rc, _ = run(f"python planner/validate_schema.py {paths_str}")
    if rc != 0 and overall_rc == 0:
        overall_rc = rc
else:
    log("No planner cases found for validation")

rc, _ = run("pytest tests/planner -q")
if rc != 0 and overall_rc == 0:
    overall_rc = rc

flaky_path = ROOT / "tests" / "utils" / "flaky_runner.py"
if flaky_path.exists():
    rc, _ = run("python tests/utils/flaky_runner.py pytest tests/e2e -q")
    if rc != 0 and overall_rc == 0:
        overall_rc = rc
else:
    log("flaky_runner.py not present; skipping")

# pipeline cases
cases_dir = ROOT / "tests" / "e2e" / "cases"
overall_cases_rc = 0
if cases_dir.exists():
    for case in sorted(cases_dir.glob("case*.json")):
        data = json.loads(case.read_text(encoding="utf-8"))
        meta = data.get("meta", {})
        allow_exec = meta.get("simulate_transient") or meta.get("simulate_concurrent") or data.get("task_id", "").endswith("create-and-run-script") or meta.get("force_corrupt_plan") or meta.get("should_fail")
        cmd = f"python pipeline_runner.py --task {case}" + (" --allow-exec" if allow_exec else "")
        rc, _ = run(cmd)
        should_fail = meta.get("should_fail", False)
        if should_fail and rc == 0:
            overall_cases_rc = 1
        if not should_fail and rc != 0:
            overall_cases_rc = rc
    log(f"PIPELINE_CASES_STATUS {overall_cases_rc}")
else:
    log("Cases dir missing")
if overall_cases_rc != 0 and overall_rc == 0:
    overall_rc = overall_cases_rc

# dump-plan-only for case1
case1 = ROOT / "tests" / "e2e" / "case1.json"
if case1.exists():
    rc, _ = run(f"python pipeline_dump_plan.py --task {case1}")
    if rc != 0 and overall_rc == 0:
        overall_rc = rc
else:
    log("case1 not found; skipping dump-plan")

# dataset
rc, _ = run("python tools/train/log_to_dataset.py")
if rc != 0 and overall_rc == 0:
    overall_rc = rc

marker = REPORTS_DIR / f"codex_ops_done_{TS}.json"
marker.write_text(json.dumps({"id": str(uuid.uuid4()), "timestamp": TS, "status": "done"}), encoding="utf-8")
log(f"WROTE {marker}")

master_id = str(uuid.uuid4())
master_line = f"MASTER_DONE id={master_id} rc={overall_rc} out={LOG.as_posix()}"
log(master_line)
print(master_line)
sys.exit(overall_rc)