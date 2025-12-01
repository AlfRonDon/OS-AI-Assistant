from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.emb.embeddings_stub import DEFAULT_DIMENSION, embed_texts  # noqa: E402
from tools.train.common import (  # noqa: E402
    REPORTS_DIR,
    SEED,
    backup_file,
    deterministic_hash,
    iso_timestamp,
    log_line,
    utc_timestamp,
)

DATA_DIR = Path("data") / "train"
SANDBOX_ROOT = Path("sandbox").resolve(strict=False)
MIN_EXAMPLES_DEFAULT = 50
BASE_DIR = Path.cwd().resolve()


@dataclass
class PipelineBlock:
    run_id: str
    task_ref: str
    dry_run: bool
    allow_exec: bool
    lines: List[str]
    plan_path: Optional[Path]
    planner_plan: Optional[Dict[str, Any]]
    raw_plan: Optional[Dict[str, Any]]
    task_json: Optional[Dict[str, Any]]
    executor_log: Optional[Path]
    rc: Optional[int]
    timestamp: str


def _parse_json_from_line(line: str, marker: str) -> Optional[Dict[str, Any]]:
    if marker not in line:
        return None
    try:
        payload = line.split(marker, 1)[1].strip()
        brace_idx = payload.find("{")
        payload = payload[brace_idx:] if brace_idx != -1 else payload
        return json.loads(payload)
    except Exception:
        return None


def _parse_plan_path(block_lines: List[str]) -> Optional[Path]:
    plan_re = re.compile(r"PLAN_WRITTEN path=([^\s]+)")
    for line in block_lines:
        match = plan_re.search(line)
        if match:
            return Path(match.group(1))
    return None


def _parse_executor_log(block_lines: List[str]) -> Optional[Path]:
    log_re = re.compile(r"executor-[a-zA-Z0-9-]+\.log")
    for line in block_lines:
        match = log_re.search(line)
        if match:
            candidate = REPORTS_DIR / match.group(0)
            if candidate.exists():
                return candidate
    return None


def _parse_rc(lines: List[str]) -> Optional[int]:
    rc_re = re.compile(r"MASTER_DONE id=[^ ]+ rc=([0-9]+)")
    for line in reversed(lines):
        match = rc_re.search(line)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                return None
    return None


def _split_blocks(lines: List[str]) -> Iterable[List[str]]:
    start_indexes = [idx for idx, line in enumerate(lines) if "PIPELINE_START" in line]
    if not start_indexes:
        return []
    start_indexes.append(len(lines))
    for idx, start in enumerate(start_indexes[:-1]):
        end = start_indexes[idx + 1]
        yield lines[start:end]


def _parse_block(block_lines: List[str]) -> Optional[PipelineBlock]:
    header = block_lines[0] if block_lines else ""
    start_match = re.search(r"PIPELINE_START id=([^\s]+) task=(.+?) dry_run=([^ ]+) allow_exec=([^ ]+)", header)
    if not start_match:
        return None
    run_id, task_ref, dry_raw, allow_raw = start_match.groups()
    dry_run = dry_raw.lower() == "true"
    allow_exec = allow_raw.lower() == "true"
    task_json = None
    raw_plan = None
    planner_plan = None
    for line in block_lines:
        if not task_json and "TASK_JSON" in line:
            task_json = _parse_json_from_line(line, "TASK_JSON")
        if not raw_plan and "PLAN_RAW" in line:
            raw_plan = _parse_json_from_line(line, "PLAN_RAW")
        if not planner_plan and "PLAN_JSON" in line:
            planner_plan = _parse_json_from_line(line, "PLAN_JSON")
    plan_path = _parse_plan_path(block_lines)
    executor_log = _parse_executor_log(block_lines)
    rc = _parse_rc(block_lines)
    timestamp = header.split("]", 1)[0].replace("[", "") if header else iso_timestamp()
    return PipelineBlock(
        run_id=run_id,
        task_ref=task_ref,
        dry_run=dry_run,
        allow_exec=allow_exec,
        lines=block_lines,
        plan_path=plan_path,
        planner_plan=planner_plan,
        raw_plan=raw_plan,
        task_json=task_json,
        executor_log=executor_log,
        rc=rc,
        timestamp=timestamp,
    )


def _resolve_sandbox_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    parts = list(candidate.parts)
    if parts and parts[0] == "sandbox":
        candidate = Path(*parts[1:])
    return (SANDBOX_ROOT / candidate).resolve(strict=False)


def _relative_to_sandbox(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(SANDBOX_ROOT).as_posix()
    except Exception:
        return path.as_posix()


def _relative_repo_path(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(BASE_DIR).as_posix()
    except Exception:
        return path.as_posix()


def _diff(before: str, after: str) -> str:
    lines_before = before.splitlines()
    lines_after = after.splitlines()
    return "\n".join(difflib.unified_diff(lines_before, lines_after, fromfile="before", tofile="after"))


def _extract_executor(log_path: Path) -> Dict[str, Any]:
    lines = log_path.read_text(encoding="utf-8").splitlines()
    rc = None
    for line in reversed(lines):
        if "RUN_END rc=" in line:
            try:
                rc = int(line.rsplit("RUN_END rc=", 1)[1])
                break
            except Exception:
                continue
    stdout_lines: List[str] = []
    stderr_lines: List[str] = []
    diffs: List[Dict[str, Any]] = []
    before: Dict[str, Any] = {}
    after: Dict[str, Any] = {}
    backup_re = re.compile(r"BACKUP path=([^ ]+) backup=([^ ]+)")

    for idx, line in enumerate(lines):
        if "STDOUT" in line:
            stdout_lines.append(line)
            if idx + 1 < len(lines):
                stdout_lines.append(lines[idx + 1])
        if "STDERR" in line:
            stderr_lines.append(line)
            if idx + 1 < len(lines):
                stderr_lines.append(lines[idx + 1])
        match = backup_re.search(line)
        if match:
            target_raw, backup_raw = match.groups()
            target = _resolve_sandbox_path(target_raw)
            backup = Path(backup_raw)
            before_text = backup.read_text(encoding="utf-8") if backup.exists() else None
            after_text = target.read_text(encoding="utf-8") if target.exists() else None
            if before_text is not None:
                before[_relative_to_sandbox(target)] = before_text
            if after_text is not None:
                after[_relative_to_sandbox(target)] = after_text
            if before_text and after_text:
                diff_text = _diff(before_text, after_text)
                if diff_text.strip():
                    diffs.append({"path": _relative_to_sandbox(target), "diff": diff_text})

    stdout = "\n".join(stdout_lines).strip()
    stderr = "\n".join(stderr_lines).strip()
    return {
        "rc": rc if rc is not None else -1,
        "stdout": stdout,
        "stderr": stderr,
        "before": before,
        "after": after,
        "diffs": diffs,
        "log": log_path.as_posix(),
    }


def _block_context(block: PipelineBlock) -> str:
    excerpt = block.lines[:8] + block.lines[-4:]
    return "\n".join(excerpt)


def _load_plan_from_path(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_record(block: PipelineBlock, skip_reasons: List[str], log_path: Optional[Path]) -> Optional[Dict[str, Any]]:
    task = block.task_json or {}
    instruction = task.get("description") or task.get("task_id") or block.task_ref
    planner_plan = block.raw_plan or block.planner_plan
    executed_plan = _load_plan_from_path(block.plan_path) or block.planner_plan or planner_plan
    executor_log = block.executor_log

    if planner_plan is None and executed_plan is None:
        skip_reasons.append(f"{block.task_ref}: missing plan data")
        log_line(log_path, f"SKIP run_id={block.run_id} reason=no plan")
        return None
    if executor_log is None:
        skip_reasons.append(f"{block.task_ref}: missing executor log")
        log_line(log_path, f"SKIP run_id={block.run_id} reason=no executor log")
        return None

    executor_data = _extract_executor(executor_log) if executor_log else None
    if not executor_data:
        skip_reasons.append(f"{block.task_ref}: executor data unavailable")
        log_line(log_path, f"SKIP run_id={block.run_id} reason=executor parse")
        return None

    dedupe_hash = deterministic_hash(
        [
            instruction,
            json.dumps(planner_plan or executed_plan, sort_keys=True),
            executor_data.get("rc"),
        ]
    )

    tags: List[str] = []
    block_text = "\n".join(block.lines).lower()
    if "compensate" in block_text or "corrupted_plan" in block_text:
        tags.append("compensated")
    if "retry" in block_text:
        tags.append("retry")
    if "permission" in block_text:
        tags.append("permission_denied")
    if block.dry_run:
        tags.append("dry_run")
    if block.allow_exec:
        tags.append("allow_exec")
    if block.rc and block.rc != 0:
        tags.append("pipeline_failed")
    if executor_data.get("rc") not in (0, None):
        tags.append("executor_failed")

    record = {
        "id": dedupe_hash,
        "instruction": instruction,
        "context": {
            "task": task,
            "log_excerpt": _block_context(block),
            "plan_path": _relative_repo_path(block.plan_path) if block.plan_path else "",
            "executor_log": _relative_repo_path(executor_log) if executor_log else "",
        },
        "plan": planner_plan,
        "executor": executor_data,
        "response": executed_plan,
        "metadata": {
            "tags": sorted(set(tags)),
            "run_id": block.run_id,
            "task_ref": block.task_ref,
            "timestamp": block.timestamp,
            "source_log": None,
            "seed": SEED,
        },
    }
    record["metadata"]["source_log"] = record["context"]["executor_log"] or block.task_ref
    record["instruction_embedding"] = embed_texts([instruction], dim=DEFAULT_DIMENSION)[0]
    return record


def _iter_pipeline_blocks(log_path: Path) -> Iterable[PipelineBlock]:
    lines = log_path.read_text(encoding="utf-8").splitlines()
    for block_lines in _split_blocks(lines):
        parsed = _parse_block(block_lines)
        if parsed:
            yield parsed


def build_dataset(out_path: Optional[Path] = None, log_path: Optional[Path] = None, min_examples: int = MIN_EXAMPLES_DEFAULT) -> Tuple[Path, int, Path, Dict[str, int]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = utc_timestamp()
    out = out_path or (DATA_DIR / f"finetune-{timestamp}.jsonl")
    skip_log = REPORTS_DIR / f"finetune-skip-{timestamp}.log"
    backup_file(out, log_path)
    skip_reasons: List[str] = []
    seen: set[str] = set()
    entries: List[Dict[str, Any]] = []
    total_candidates = 0
    duplicate_count = 0

    for pipeline_log in sorted(REPORTS_DIR.glob("pipeline-*.log")):
        for block in _iter_pipeline_blocks(pipeline_log):
            record = _build_record(block, skip_reasons, log_path)
            if not record:
                continue
            total_candidates += 1
            if record["id"] in seen:
                skip_reasons.append(f"{record['metadata']['task_ref']}: duplicate hash {record['id']}")
                log_line(log_path, f"SKIP run_id={block.run_id} reason=duplicate")
                duplicate_count += 1
                continue
            record["metadata"]["source_log"] = pipeline_log.as_posix()
            seen.add(record["id"])
            entries.append(record)

    entries.sort(key=lambda rec: (rec["metadata"].get("source_log", ""), rec["metadata"].get("timestamp", ""), rec["id"]))

    with out.open("w", encoding="utf-8") as handle:
        for rec in entries:
            handle.write(json.dumps(rec, ensure_ascii=True) + "\n")

    if skip_reasons:
        skip_log.parent.mkdir(parents=True, exist_ok=True)
        skip_log.write_text("\n".join(skip_reasons), encoding="utf-8")
    else:
        skip_log.touch()

    written = len(entries)
    if written < min_examples and written > 0:
        log_line(log_path, f"DATASET_BELOW_MIN written={written} min_required={min_examples}")
    log_line(log_path, f"DATASET_WRITTEN path={out.as_posix()} rows={written} candidates={total_candidates} duplicates={duplicate_count}")
    stats = {"rows": written, "candidates": total_candidates, "duplicates": duplicate_count, "skipped": len(skip_reasons)}
    return out, written, skip_log, stats


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate finetuning dataset from pipeline and executor logs.")
    parser.add_argument("--out", help="Optional output path; defaults to data/train/finetune-<ts>.jsonl")
    parser.add_argument("--log", help="Path to append run logs; defaults to reports/finetune-<ts>.log")
    parser.add_argument("--min", dest="min_examples", type=int, default=MIN_EXAMPLES_DEFAULT, help="Minimum desired examples before warning.")
    args = parser.parse_args(argv)

    ts = utc_timestamp()
    log_path = Path(args.log) if args.log else REPORTS_DIR / f"finetune-{ts}.log"
    out_path = Path(args.out) if args.out else None

    try:
        out, rows, skip_log, stats = build_dataset(out_path=out_path, log_path=log_path, min_examples=args.min_examples)
        print(f"DATASET rows={rows} out={out.as_posix()} skip_log={skip_log.as_posix()} stats={stats}")
        print(f"MASTER_DONE id={uuid.uuid4()} rc=0 out={log_path.as_posix()}")
        return 0
    except Exception as exc:  # pragma: no cover - defensive CLI guard
        log_line(log_path, f"DATASET_ERROR {exc}")
        print(f"MASTER_DONE id={uuid.uuid4()} rc=1 out={log_path.as_posix()}")
        return 1


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
