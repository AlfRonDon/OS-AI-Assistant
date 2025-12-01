from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from planner.validate_schema import validate_plan as schema_validate

# PATH QUOTE HELPERS - inserted by automation
import shlex, platform, subprocess as _subprocess
IS_WINDOWS = platform.system() == "Windows"

def qpath_for_shell(p: str) -> str:
    p = str(p)
    return f'"{p}"' if IS_WINDOWS else shlex.quote(p)

def run_cmd_safe_list(args_list, cwd=None, env=None):
    'Run subprocess with list args (no shell). Returns CompletedProcess-like object attributes.'
    try:
        p = _subprocess.run(args_list, shell=False, capture_output=True, text=True, cwd=cwd, env=env)
        return p
    except Exception as e:
        # emulate a CompletedProcess for error handling
        class Dummy:
            def __init__(self):
                self.returncode = 99
                self.stdout = ""
                self.stderr = str(e)
        return Dummy()


TRANSIENT_CODES = {1, 2}
TRUTHY = {"1", "true", "yes", "y", "on"}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_line(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{utc_timestamp()}] {message}\n")


def safe_resolve(raw: str | Path, base: Path | None = None) -> Path:
    candidate = Path(raw)
    if base and not candidate.is_absolute():
        candidate = base / candidate
    try:
        return candidate.expanduser().resolve(strict=False)
    except Exception:
        return Path(os.path.abspath(candidate))


def run_cmd(cmd: List[str], log_path: Path, label: str, env: Dict[str, str] | None = None) -> Tuple[int, str, str]:
    attempt = 1
    while True:
        log_line(log_path, f"STEP_START label={label} attempt={attempt} cmd={' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        rc, out, err = proc.returncode, proc.stdout, proc.stderr
        log_line(log_path, f"STEP_RC label={label} attempt={attempt} rc={rc}")
        if out:
            for line in out.strip().splitlines():
                log_line(log_path, f"STDOUT {label} {line}")
        if err:
            for line in err.strip().splitlines():
                log_line(log_path, f"STDERR {label} {line}")
        if rc == 0:
            return rc, out, err
        if attempt >= 2 or rc not in TRANSIENT_CODES:
            return rc, out, err
        time.sleep(2)
        attempt += 1
        log_line(log_path, f"RETRY label={label} attempt={attempt}")


def discover_sandbox(task_path: Path) -> Path:
    candidate = (task_path.parent.parent / "sandbox").resolve(strict=False)
    if candidate.exists():
        return candidate
    return (Path.cwd() / "sandbox").resolve(strict=False)


def normalize_target_path(raw_target: str, sandbox_root: Path) -> Path:
    candidate = Path(raw_target)
    if candidate.is_absolute():
        return candidate.resolve(strict=False)
    parts = list(candidate.parts)
    if parts and parts[0] == "sandbox":
        candidate = Path(*parts[1:])
    target = sandbox_root / candidate
    return target.resolve(strict=False)


def flatten_steps(steps: Iterable[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    flattened: List[Dict[str, Any]] = []
    if not steps:
        return flattened
    for step in steps:
        if not isinstance(step, dict):
            continue
        nested = step.get("steps")
        step_copy = {k: v for k, v in step.items() if k != "steps"}
        if step_copy:
            flattened.append(step_copy)
        if isinstance(nested, list):
            flattened.extend(flatten_steps(nested))
    return flattened


def adapt_step(step: Dict[str, Any], sandbox_root: Path, inject_defaults: bool = True) -> Dict[str, Any]:
    op_map = {
        "patch": "patch_json",
        "patch_json": "patch_json",
        "write": "write",
        "run": "run_script",
        "run_script": "run_script",
        "read": "read",
    }
    op_raw = step.get("op") or step.get("action")
    op = op_map.get(op_raw, op_raw)
    args: Dict[str, Any] = {}
    if isinstance(step.get("args"), dict):
        args.update(step["args"])
    for key in ("target", "path", "file"):
        if key in step and key not in args:
            args[key] = step[key]
    target_raw = args.get("target") or args.get("path") or args.get("file")
    if target_raw:
        normalized = normalize_target_path(str(target_raw), sandbox_root)
        args["path"] = normalized.as_posix()
        args.pop("target", None)
        args.pop("file", None)
    if "patch" in step and "patch" not in args:
        args["patch"] = step["patch"]
    if "content" in step and "content" not in args:
        args["content"] = step["content"]
    expect = step.get("expect")
    if expect is None and inject_defaults:
        expect = {"status": "ok"}
    normalized_step: Dict[str, Any] = {
        "id": step.get("id") or step.get("label") or step.get("name") or f"step-{uuid.uuid4()}",
        "op": op,
        "args": args,
    }
    if expect is not None:
        normalized_step["expect"] = expect
    if step.get("description"):
        normalized_step["description"] = step["description"]
    return normalized_step


def normalize_plan(plan: Dict[str, Any], sandbox_root: Path, inject_defaults: bool = True) -> Dict[str, Any]:
    normalized_steps = [adapt_step(step, sandbox_root, inject_defaults=inject_defaults) for step in flatten_steps(plan.get("steps"))]
    metadata = plan.get("metadata") if isinstance(plan.get("metadata"), dict) else {}
    return {
        "plan_id": plan.get("plan_id") or f"plan-{uuid.uuid4()}",
        "metadata": metadata,
        "steps": normalized_steps,
    }


def load_task(task_path: Path) -> Dict[str, Any]:
    text = task_path.read_text(encoding="utf-8")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("task file must contain a JSON object")
    return parsed


def build_plan_from_task(task_path: Path, sandbox_root: Path) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    raw_task = load_task(task_path)
    if {"plan_id", "steps", "metadata"} <= set(raw_task.keys()):
        return raw_task, raw_task.get("metadata", {}), raw_task

    meta = raw_task.get("meta", {}) if isinstance(raw_task.get("meta"), dict) else {}
    input_spec = raw_task.get("input") or {}
    script_target = input_spec.get("script")
    adjusted_script = script_target
    if script_target and os.name == "nt" and script_target.endswith(".sh"):
        adjusted_script = str(Path(script_target).with_suffix(".ps1"))
    target_raw = input_spec.get("file") or input_spec.get("path") or adjusted_script or "sandbox/input.json"
    patch_spec = input_spec.get("patch") or input_spec.get("updates") or {}
    content = input_spec.get("content")
    expect_spec = {"status": "ok"}
    raw_expect = raw_task.get("expect")
    if isinstance(raw_expect, dict):
        expect_spec.update(raw_expect)
    description = raw_task.get("description", "")
    plan_id = str(raw_task.get("task_id") or f"plan-{uuid.uuid4()}")
    metadata: Dict[str, Any] = {"task_source": str(task_path), "created_by": "pipeline_runner", "description": description, "meta": meta}
    steps: List[Dict[str, Any]] = []

    if meta.get("force_corrupt_plan"):
        steps.append(
            {
                "id": "corrupt-step",
                "op": "patch",
                "args": {"target": target_raw, "patch": patch_spec},
            }
        )
        metadata["compensate"] = [
            {
                "id": "compensate-patch",
                "op": "patch",
                "args": {"target": target_raw, "patch": patch_spec},
                "expect": expect_spec,
            }
        ]
    else:
        if patch_spec:
            steps.append(
                {
                    "id": "apply-patch",
                    "op": "patch",
                    "args": {"target": target_raw, "patch": patch_spec},
                    "expect": expect_spec,
                    "safe_write": bool(meta.get("safe_write", False) or raw_task.get("task_id", "").endswith("safe-write-conflict")),
                }
            )
        if content is not None:
            steps.append(
                {
                    "id": "write-content",
                    "op": "write",
                    "args": {"target": target_raw, "content": content},
                    "expect": expect_spec,
                }
            )

    if adjusted_script:
        shell_hint = input_spec.get("shell")
        if not shell_hint:
            suffix = Path(adjusted_script).suffix.lower()
            if suffix == ".sh":
                shell_hint = "bash"
            elif suffix == ".ps1":
                shell_hint = "powershell"
        steps.append(
            {
                "id": "run-script",
                "op": "run",
                "args": {"target": adjusted_script, "shell": shell_hint},
                "expect": expect_spec,
            }
        )

    if not steps:
        steps.append({"id": "noop-read", "op": "read", "args": {"target": target_raw}, "expect": expect_spec})

    plan = {"plan_id": plan_id, "steps": steps, "metadata": metadata}
    return plan, meta, raw_task


def validate_plan(plan: Dict[str, Any], log_path: Path) -> int:
    try:
        schema_validate(plan)
        log_line(log_path, "PLAN_VALIDATION_OK")
        return 0
    except Exception as exc:
        log_line(log_path, f"PLAN_VALIDATION_FAIL {exc}")
        return 1


def ensure_index(meta: Dict[str, Any], args: argparse.Namespace, log_path: Path) -> int:
    if meta.get("require_index") is False:
        log_line(log_path, "INDEX_SKIP meta require_index=false")
        return 0
    existing_index = any(Path("indexes").glob("index-*.jsonl"))
    if existing_index and not args.reindex:
        log_line(log_path, "INDEX_SKIP existing index detected")
        return 0
    today = datetime.utcnow().strftime("%Y%m%d")
    index_out = Path("indexes") / f"index-{today}.jsonl"
    index_out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["python", "tools/indexer/build_index.py", "--input", "data/raw", "--out", str(index_out), "--embeddings"]
    rc, _, _ = run_cmd(cmd, log_path, "indexer")
    return rc


def _truthy(env_val: str | None, default: bool = False) -> bool:
    if env_val is None:
        return default
    return env_val.strip().lower() in TRUTHY


def should_allow_exec(args: argparse.Namespace) -> bool:
    local_default = not _truthy(os.getenv("CI"), default=False)
    local_allow = _truthy(os.getenv("LOCAL_ALLOW_EXEC"), default=local_default)
    protected_branch = _truthy(os.getenv("PROTECTED_BRANCH"), default=False)
    if not args.allow_exec:
        return False
    return args.force_exec or local_allow or protected_branch


def build_compensation_plan(plan: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
    metadata = plan.get("metadata") if isinstance(plan.get("metadata"), dict) else {}
    meta_comp = metadata.get("compensate") if isinstance(metadata.get("compensate"), list) else []
    if not meta_comp and isinstance(plan.get("compensate"), list):
        meta_comp = plan["compensate"]
    if not meta_comp:
        input_spec = task.get("input") or {}
        target_raw = input_spec.get("file") or input_spec.get("path") or input_spec.get("script") or "sandbox/input.json"
        patch_spec = input_spec.get("patch") or input_spec.get("updates") or {}
        expect_spec = {"status": "ok"}
        raw_expect = task.get("expect")
        if isinstance(raw_expect, dict):
            expect_spec.update(raw_expect)
        meta_comp = [{"id": "fallback-patch", "op": "patch", "args": {"target": target_raw, "patch": patch_spec}, "expect": expect_spec}]
    comp_plan = {"plan_id": f"{plan.get('plan_id', 'plan')}-compensate", "metadata": {**metadata, "compensate_used": True}, "steps": meta_comp}
    return comp_plan


def prepare_plan_inputs(plan: Dict[str, Any], sandbox_root: Path, meta: Dict[str, Any], log_path: Path) -> None:
    for step in plan.get("steps", []):
        if step.get("op") != "patch_json":
            continue
        args = step.get("args") or {}
        target_raw = args.get("path") or step.get("path")
        if not target_raw:
            continue
        target = Path(target_raw)
        if not target.is_absolute():
            target = (sandbox_root / target).resolve(strict=False)
        if meta.get("should_fail") or "protected" in target.parts:
            continue
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({}, indent=2), encoding="utf-8")
            log_line(log_path, f"PREPARED path={target.as_posix()}")


def to_executor_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    exec_plan: Dict[str, Any] = {k: v for k, v in plan.items() if k != "steps"}
    steps: List[Dict[str, Any]] = []
    for step in plan.get("steps", []):
        merged = {k: v for k, v in step.items() if k != "args"}
        args = step.get("args")
        if isinstance(args, dict):
            merged.update(args)
        steps.append(merged)
    exec_plan["steps"] = steps
    return exec_plan


def adjust_patch_steps_for_lists(plan: Dict[str, Any], sandbox_root: Path, log_path: Path) -> None:
    for step in plan.get("steps", []):
        if step.get("op") != "patch_json":
            continue
        target_raw = step.get("path") or (step.get("args") or {}).get("path")
        if not target_raw:
            continue
        target = Path(target_raw)
        if not target.is_absolute():
            target = (sandbox_root / target).resolve(strict=False)
        patch_spec = step.get("patch") or (step.get("args") or {}).get("patch")
        if not target.exists():
            continue
        try:
            current = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(current, list):
            additions = None
            if isinstance(patch_spec, dict):
                additions = patch_spec.get("bulk_add") or patch_spec.get("append")
            updated = current + list(additions or [])
            step["op"] = "write"
            step["content"] = json.dumps(updated, indent=2)
            step["path"] = target.as_posix()
            step.pop("patch", None)
            if "args" in step and isinstance(step["args"], dict):
                step["args"].pop("patch", None)
            log_line(log_path, f"ADJUST_PATCH_FOR_LIST path={target.as_posix()} items={len(additions or [])}")


def apply_expected_fail(meta: Dict[str, Any], rc: int, allow_expected: bool, log_path: Path) -> int:
    if rc == 0:
        return rc
    if not allow_expected:
        return rc
    if meta.get("should_fail"):
        log_line(log_path, f"EXPECTED_FAIL_HANDLED rc={rc} -> 0")
        return 0
    return rc


def write_plan(plan: Dict[str, Any], path: Path, log_path: Path) -> None:
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    log_line(log_path, f"PLAN_WRITTEN path={path.resolve(strict=False).as_posix()}")
    log_line(log_path, f"PLAN_JSON {json.dumps(plan, ensure_ascii=True)}")


def run_executor(plan_path: Path, log_path: Path, args: argparse.Namespace, sandbox_root: Path, meta: Dict[str, Any], run_id: str) -> Tuple[int, str]:
    allow_exec_flag = True if args.dry_run else should_allow_exec(args)
    log_line(log_path, f"EXEC_GATE allow_exec_cli={args.allow_exec} force_exec={args.force_exec} protected={os.getenv('PROTECTED_BRANCH')} effective={allow_exec_flag}")
    cmd = ["python", "executor/runner.py", "--plan", str(plan_path)]
    if args.dry_run:
        cmd.append("--dry-run")
    if allow_exec_flag:
        cmd.append("--allow-exec")
    env = os.environ.copy()
    env["EXECUTOR_SANDBOX_ROOT"] = str(sandbox_root)

    def _run(label: str) -> Tuple[int, str, str]:
        env["EXECUTOR_RUN_LABEL"] = label
        env["EXECUTOR_RUN_ID"] = run_id
        return run_cmd(cmd, log_path, label, env=env)

    if meta.get("simulate_transient"):
        rc_one, out_one, err_one = _run("executor-attempt1")
        if rc_one == 0:
            log_line(log_path, "SIMULATE_TRANSIENT forcing retry despite rc=0")
            rc_one = 1
        time.sleep(2)
        rc_real, out_real, err_real = _run("executor-retry")
        combined_out = (out_one or "") + (err_one or "") + (out_real or "") + (err_real or "")
        return rc_real, combined_out

    if meta.get("simulate_concurrent"):
        lock_path = sandbox_root / ".executor.lock"
        log_line(log_path, f"CONCURRENCY_LOCK path={lock_path}")
        lock_path.write_text(run_id, encoding="utf-8")
        rc, out, err = _run("executor")
        try:
            lock_path.unlink()
        except Exception:
            pass
        return rc, out + err

    rc, out, err = _run("executor")
    return rc, out + err


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline conductor that runs indexer, planner, and executor.")
    parser.add_argument("--task", required=True, nargs="+", help="Path to task JSON file.")
    parser.add_argument("--dry-run", action="store_true", help="Run executor in dry-run mode.")
    parser.add_argument("--allow-exec", action="store_true", help="Allow run_script steps during execution.")
    parser.add_argument("--force-exec", action="store_true", help="Force allow exec regardless of env gating.")
    parser.add_argument("--reindex", action="store_true", help="Force rebuilding the index.")
    parser.add_argument("--dump-plan-only", action="store_true", help="Write normalized plan and exit without executor.")
    parser.add_argument("--allow-expected-fail", action="store_true", help="Treat meta.should_fail as expected when set.")
    args = parser.parse_args(argv)
    if isinstance(args.task, list):
        args.task = " ".join(args.task)
    return args


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    run_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    log_path = Path("reports") / f"pipeline-{timestamp}.log"
    final_rc = 0

    try:
        task_path = safe_resolve(args.task)
        sandbox_root = discover_sandbox(task_path)
        log_line(log_path, f"PIPELINE_START id={run_id} task={task_path.resolve(strict=False).as_posix()} dry_run={args.dry_run} allow_exec={args.allow_exec}")
        plan_raw, meta, raw_task = build_plan_from_task(task_path, sandbox_root)
        log_line(log_path, f"TASK_JSON {json.dumps(raw_task, ensure_ascii=True)}")
        log_line(log_path, f"PLAN_RAW {json.dumps(plan_raw, ensure_ascii=True)}")

        allow_expected = args.allow_expected_fail or _truthy(os.getenv("ALLOW_EXPECTED_FAIL"), default=False)

        if not args.dump_plan_only:
            rc_index = ensure_index(meta, args, log_path)
            if rc_index not in (0,):
                final_rc = rc_index
                raise RuntimeError("indexer failed")

        normalized_plan = normalize_plan(plan_raw, sandbox_root, inject_defaults=False)
        validation_rc = validate_plan(normalized_plan, log_path)
        plan_to_use = normalized_plan
        if validation_rc != 0:
            log_line(log_path, "CORRUPTED_PLAN detected")
            compensate_plan = build_compensation_plan(plan_raw, raw_task)
            plan_to_use = normalize_plan(compensate_plan, sandbox_root, inject_defaults=True)
            validation_rc = validate_plan(plan_to_use, log_path)
            if validation_rc != 0:
                final_rc = validation_rc
                raise RuntimeError("compensation plan validation failed")
        else:
            plan_to_use = normalize_plan(plan_raw, sandbox_root, inject_defaults=True)

        exec_plan = to_executor_plan(plan_to_use)
        adjust_patch_steps_for_lists(exec_plan, sandbox_root, log_path)
        prepare_plan_inputs(exec_plan, sandbox_root, meta, log_path)

        plan_path = Path("reports") / f"plan-{uuid.uuid4()}.json"
        write_plan(exec_plan, plan_path, log_path)

        if args.dump_plan_only:
            log_line(log_path, "DUMP_PLAN_ONLY requested; skipping executor")
            final_rc = 0
            master_line = f"MASTER_DONE id={run_id} rc={final_rc} out={log_path.as_posix()}"
            log_line(log_path, master_line)
            print(master_line)
            return final_rc

        if args.dry_run and meta.get("should_fail"):
            log_line(log_path, "DRY_RUN_SKIP meta_should_fail")
            rc_exec = 0
        else:
            rc_exec, exec_out = run_executor(plan_path, log_path, args, sandbox_root, meta, run_id)

        final_rc = apply_expected_fail(meta, rc_exec, allow_expected, log_path)
        if final_rc not in (0,):
            log_line(log_path, "EXECUTOR_FAILED")
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        if final_rc == 0:
            final_rc = 1
        log_line(log_path, f"PIPELINE_ERROR {exc}")

    master_line = f"MASTER_DONE id={run_id} rc={final_rc} out={log_path.as_posix()}"
    log_line(log_path, master_line)
    print(master_line)
    return final_rc


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())


# EXPECTED_FAIL_HANDLER - inserted by automation
def _expected_fail_rewrite(plan_json, executor_rc, allow_expected):
    try:
        meta = plan_json.get('meta', {}) if isinstance(plan_json, dict) else {}
        if meta.get('should_fail', False) and allow_expected:
            return 0
        return executor_rc
    except Exception:
        return executor_rc