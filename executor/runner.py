from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jsonschema import ValidationError, validate


@dataclass
class StepResult:
    success: bool
    rc: int
    stdout: str = ""
    stderr: str = ""
    attempt: int = 1
    label: str = ""
    op: str = ""


class ExecutionContext:
    def __init__(self, sandbox: Path, allow_exec: bool, dry_run: bool, log_path: Path):
        self.sandbox = sandbox
        self.allow_exec = allow_exec
        self.dry_run = dry_run
        self.log_path = log_path


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_line(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{utc_timestamp()}] {message}\n")


def ensure_sandbox(base: Path) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def resolve_in_sandbox(raw_path: str, sandbox: Path) -> Path:
    if not raw_path:
        raise ValueError("path is required for this operation")
    candidate = Path(raw_path)
    resolved = candidate if candidate.is_absolute() else (sandbox / candidate)
    resolved = resolved.resolve()
    sandbox_root = sandbox.resolve()
    try:
        inside = resolved.is_relative_to(sandbox_root)
    except AttributeError:
        try:
            resolved.relative_to(sandbox_root)
            inside = True
        except ValueError:
            inside = False
    if not inside:
        raise ValueError(f"refusing to operate outside sandbox: {resolved}")
    return resolved


def create_backup(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    backup_path = path.with_name(path.name + ".bak")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return backup_path


def deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for key in set(base.keys()) | set(patch.keys()):
        base_val = base.get(key)
        patch_val = patch.get(key)
        if isinstance(base_val, dict) and isinstance(patch_val, dict):
            merged[key] = deep_merge(base_val, patch_val)
        else:
            merged[key] = patch_val if key in patch else base_val
    return merged


def load_schema(schema_spec: Any, sandbox: Path) -> Optional[Dict[str, Any]]:
    if schema_spec is None:
        return None
    if isinstance(schema_spec, dict):
        return schema_spec
    if isinstance(schema_spec, str):
        schema_path = resolve_in_sandbox(schema_spec, sandbox)
        return json.loads(schema_path.read_text(encoding="utf-8"))
    raise ValueError("schema must be a dict or path string")


def perform_read(step: Dict[str, Any], ctx: ExecutionContext, label: str, attempt: int) -> StepResult:
    path = resolve_in_sandbox(step.get("path", ""), ctx.sandbox)
    if ctx.dry_run:
        stdout = f"DRY-RUN read {path}"
        return StepResult(True, 0, stdout=stdout, attempt=attempt, label=label, op="read")
    try:
        data = path.read_text(encoding="utf-8")
        return StepResult(True, 0, stdout=data, attempt=attempt, label=label, op="read")
    except Exception as exc:  # pragma: no cover - defensive
        return StepResult(False, 4, stderr=str(exc), attempt=attempt, label=label, op="read")


def perform_write(step: Dict[str, Any], ctx: ExecutionContext, label: str, attempt: int) -> StepResult:
    path = resolve_in_sandbox(step.get("path", ""), ctx.sandbox)
    content = step.get("content", "")
    if ctx.dry_run:
        stdout = f"DRY-RUN write to {path}"
        return StepResult(True, 0, stdout=stdout, attempt=attempt, label=label, op="write")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = create_backup(path)
        if backup:
            log_line(ctx.log_path, f"BACKUP path={path} backup={backup}")
        path.write_text(content, encoding="utf-8")
        return StepResult(True, 0, stdout=f"wrote {len(content)} bytes to {path}", attempt=attempt, label=label, op="write")
    except Exception as exc:  # pragma: no cover - defensive
        return StepResult(False, 4, stderr=str(exc), attempt=attempt, label=label, op="write")


def perform_patch_json(step: Dict[str, Any], ctx: ExecutionContext, label: str, attempt: int) -> StepResult:
    path = resolve_in_sandbox(step.get("path", ""), ctx.sandbox)
    patch_spec = step.get("patch") or step.get("updates") or {}
    if not isinstance(patch_spec, dict):
        return StepResult(False, 4, stderr="patch_json requires 'patch' dict", attempt=attempt, label=label, op="patch_json")
    try:
        original_text = path.read_text(encoding="utf-8")
        original_json = json.loads(original_text)
    except Exception as exc:  # pragma: no cover - defensive
        return StepResult(False, 4, stderr=f"failed to read json: {exc}", attempt=attempt, label=label, op="patch_json")
    updated = deep_merge(original_json, patch_spec)
    try:
        schema = load_schema(step.get("schema"), ctx.sandbox)
        if schema:
            validate(updated, schema)
    except ValidationError as exc:
        return StepResult(False, 4, stderr=f"schema validation failed: {exc.message}", attempt=attempt, label=label, op="patch_json")
    except Exception as exc:  # pragma: no cover - defensive
        return StepResult(False, 4, stderr=f"schema load failed: {exc}", attempt=attempt, label=label, op="patch_json")
    if ctx.dry_run:
        return StepResult(True, 0, stdout=f"DRY-RUN patch_json {path}", attempt=attempt, label=label, op="patch_json")
    try:
        backup = create_backup(path)
        if backup:
            log_line(ctx.log_path, f"BACKUP path={path} backup={backup}")
        path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
        return StepResult(True, 0, stdout=f"patched json at {path}", attempt=attempt, label=label, op="patch_json")
    except Exception as exc:  # pragma: no cover - defensive
        return StepResult(False, 4, stderr=str(exc), attempt=attempt, label=label, op="patch_json")


def choose_shell(preferred: str) -> Tuple[str, List[str]]:
    shell = (preferred or "").lower()
    candidates: List[Tuple[str, List[str]]] = []
    if shell in ("pwsh", "powershell", "ps"):
        candidates.append(("pwsh", ["pwsh", "-NoLogo", "-NonInteractive"]))
        candidates.append(("powershell", ["powershell", "-NoLogo", "-NonInteractive"]))
    elif shell in ("bash", "sh"):
        candidates.append(("bash", ["bash"]))
        candidates.append(("sh", ["sh"]))
    else:
        candidates.append(("pwsh", ["pwsh", "-NoLogo", "-NonInteractive"]))
        candidates.append(("powershell", ["powershell", "-NoLogo", "-NonInteractive"]))
        candidates.append(("bash", ["bash"]))
        candidates.append(("sh", ["sh"]))

    for name, command in candidates:
        if shutil.which(command[0]):
            return name, command
    raise RuntimeError("no shell available for run_script")


def perform_run_script(step: Dict[str, Any], ctx: ExecutionContext, label: str, attempt: int) -> StepResult:
    if not ctx.allow_exec:
        return StepResult(False, 2, stderr="run_script blocked: --allow-exec not set", attempt=attempt, label=label, op="run_script")
    script_body = step.get("script") or step.get("command")
    script_path_raw = step.get("path")
    shell_pref = step.get("shell") or step.get("interpreter") or ""
    resolved_path: Optional[Path] = None
    if not script_body and not script_path_raw:
        return StepResult(False, 4, stderr="run_script requires 'script' or 'path'", attempt=attempt, label=label, op="run_script")
    if script_path_raw:
        try:
            resolved_path = resolve_in_sandbox(script_path_raw, ctx.sandbox)
        except Exception as exc:
            return StepResult(False, 4, stderr=str(exc), attempt=attempt, label=label, op="run_script")
    try:
        shell_name, shell_command = choose_shell(shell_pref)
    except Exception as exc:
        return StepResult(False, 4, stderr=str(exc), attempt=attempt, label=label, op="run_script")
    if ctx.dry_run:
        location = str(resolved_path) if resolved_path else "<inline>"
        stdout = f"DRY-RUN run_script {location} using {shell_name}"
        return StepResult(True, 0, stdout=stdout, attempt=attempt, label=label, op="run_script")
    if resolved_path:
        if shell_name in ("bash", "sh"):
            command = shell_command + [str(resolved_path)]
        else:
            command = shell_command + ["-File", str(resolved_path)]
    else:
        if shell_name in ("bash", "sh"):
            command = shell_command + ["-lc", script_body]
        else:
            command = shell_command + ["-Command", script_body]
    proc = subprocess.run(command, capture_output=True, text=True, cwd=ctx.sandbox)
    success = proc.returncode == 0
    return StepResult(success, proc.returncode, stdout=proc.stdout, stderr=proc.stderr, attempt=attempt, label=label, op="run_script")


STEP_HANDLERS = {
    "read": perform_read,
    "write": perform_write,
    "patch_json": perform_patch_json,
    "run_script": perform_run_script,
}


def log_step_result(ctx: ExecutionContext, result: StepResult) -> None:
    status = "success" if result.success else "fail"
    log_line(ctx.log_path, f"STEP_DONE label={result.label} op={result.op} attempt={result.attempt} rc={result.rc} status={status}")
    if ctx.dry_run:
        preview = result.stdout or f"DRY-RUN {result.op} {result.label} status={status}"
        print(preview)
    if result.stdout:
        snippet = result.stdout.strip()
        log_line(ctx.log_path, f"STDOUT label={result.label} len={len(result.stdout)}")
        log_line(ctx.log_path, snippet)
    if result.stderr:
        snippet = result.stderr.strip()
        log_line(ctx.log_path, f"STDERR label={result.label} len={len(result.stderr)}")
        log_line(ctx.log_path, snippet)


def execute_step(step: Dict[str, Any], ctx: ExecutionContext, label: str, attempt: int) -> StepResult:
    op = step.get("op") or step.get("action")
    if op not in STEP_HANDLERS:
        result = StepResult(False, 4, stderr=f"unsupported op: {op}", attempt=attempt, label=label, op=str(op))
        log_step_result(ctx, result)
        return result
    log_line(ctx.log_path, f"STEP_START label={label} op={op} attempt={attempt}")
    handler = STEP_HANDLERS[op]
    result = handler(step, ctx, label, attempt)
    log_step_result(ctx, result)
    return result


def execute_with_retry(step: Dict[str, Any], ctx: ExecutionContext, label: str) -> StepResult:
    attempt = 1
    result = execute_step(step, ctx, label, attempt)
    if result.success or result.rc == 2:
        return result
    attempt += 1
    log_line(ctx.log_path, f"RETRY label={label} attempt={attempt}")
    return execute_step(step, ctx, label, attempt)


def compensation_steps(step: Dict[str, Any], plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(step.get("compensate"), list):
        return step["compensate"]
    if isinstance(plan.get("compensate"), list):
        return plan["compensate"]
    return []


def run_compensation(steps: List[Dict[str, Any]], ctx: ExecutionContext) -> bool:
    all_ok = True
    for idx, comp in enumerate(steps, 1):
        label = comp.get("label") or comp.get("name") or f"compensate-{idx}"
        result = execute_with_retry(comp, ctx, label)
        if not result.success:
            all_ok = False
    return all_ok


def run_plan(plan: Dict[str, Any], ctx: ExecutionContext) -> int:
    steps = plan.get("steps")
    if not isinstance(steps, list):
        log_line(ctx.log_path, "PLAN_ERROR missing steps list")
        return 4
    final_rc = 0
    for idx, step in enumerate(steps, 1):
        label = step.get("label") or step.get("name") or f"step-{idx}"
        result = execute_with_retry(step, ctx, label)
        if result.success:
            continue
        final_rc = result.rc if result.rc == 2 else 4
        comp_steps = compensation_steps(step, plan)
        if comp_steps:
            log_line(ctx.log_path, f"COMPENSATE_START for={label}")
            if run_compensation(comp_steps, ctx) and final_rc != 2:
                final_rc = 3
            log_line(ctx.log_path, f"COMPENSATE_DONE for={label}")
        break
    return final_rc


def load_plan(plan_path: Path) -> Dict[str, Any]:
    return json.loads(plan_path.read_text(encoding="utf-8"))


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Executor v0.1 safe runner")
    parser.add_argument("--plan", required=True, help="Path to plan JSON")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without changing disk")
    parser.add_argument("--allow-exec", action="store_true", help="Allow run_script steps to execute")
    parser.add_argument("--id", dest="run_id", help="Optional run id")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    sandbox_override = os.getenv("EXECUTOR_SANDBOX_ROOT")
    sandbox_base = Path(sandbox_override) if sandbox_override else root / "sandbox"
    sandbox = ensure_sandbox(sandbox_base)
    run_id = args.run_id or str(uuid.uuid4())
    log_path = (root / "reports" / f"executor-{run_id}.log").resolve()
    ctx = ExecutionContext(sandbox=sandbox, allow_exec=args.allow_exec, dry_run=args.dry_run, log_path=log_path)
    try:
        plan = load_plan(Path(args.plan))
    except Exception as exc:  # pragma: no cover - defensive
        log_line(ctx.log_path, f"PLAN_LOAD_ERROR {exc}")
        print(f"MASTER_DONE id={run_id} rc=4 out=reports/executor-{run_id}.log")
        return 4
    log_line(ctx.log_path, f"RUN_START id={run_id} plan={args.plan} dry_run={args.dry_run} allow_exec={args.allow_exec}")
    rc = run_plan(plan, ctx)
    log_line(ctx.log_path, f"RUN_END rc={rc}")
    print(f"MASTER_DONE id={run_id} rc={rc} out=reports/executor-{run_id}.log")
    return rc


if __name__ == "__main__":
    sys.exit(main())
