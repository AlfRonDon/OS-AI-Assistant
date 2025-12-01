from __future__ import annotations

import difflib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

REPORTS_DIR = Path("reports")
OUT_DIR = Path("data") / "train"
SANDBOX_ROOT = Path("sandbox").resolve(strict=False)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _iter_logs() -> Iterable[Path]:
    if not REPORTS_DIR.exists():
        return []
    for pattern in ("pipeline-*.log", "executor-*.log"):
        for path in sorted(REPORTS_DIR.glob(pattern)):
            yield path


def _parse_json_line(lines: List[str], prefix: str) -> Optional[Any]:
    for line in lines:
        if prefix in line:
            payload = line.split(prefix, 1)[1].strip()
            try:
                return json.loads(payload)
            except Exception:
                continue
    return None


def _parse_rc(lines: List[str]) -> Optional[int]:
    joined = "\n".join(lines)
    match = re.search(r"MASTER_DONE id=[0-9a-fA-F-]+ rc=([0-9]+)", joined)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return None
    return None


def _try_load_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return text


def _collect_modified_paths(lines: List[str]) -> List[Path]:
    paths: List[Path] = []
    backup_re = re.compile(r"BACKUP path=([^ ]+)")
    patched_re = re.compile(r"patched json at ([^ ]+)")
    write_re = re.compile(r"wrote .* to ([^ ]+)")
    for line in lines:
        for matcher in (backup_re, patched_re, write_re):
            match = matcher.search(line)
            if match:
                candidate = Path(match.group(1))
                paths.append(candidate)
    return paths


def _resolve_candidate(path: Path) -> Path:
    if path.is_absolute():
        return path.resolve(strict=False)
    parts = list(path.parts)
    candidate = path
    if parts and parts[0] == "sandbox":
        candidate = Path(*parts[1:])
    return (SANDBOX_ROOT / candidate).resolve(strict=False)


def _diff(before: str, after: str) -> str:
    lines_before = before.splitlines()
    lines_after = after.splitlines()
    return "\n".join(difflib.unified_diff(lines_before, lines_after, fromfile="before", tofile="after"))


def _extract_log_record(log_path: Path) -> Optional[Dict[str, Any]]:
    marker = OUT_DIR / f"processed-{log_path.name}.done"
    if marker.exists():
        return None

    text = log_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    rc = _parse_rc(lines)
    task = _parse_json_line(lines, "TASK_JSON")
    plan = _parse_json_line(lines, "PLAN_JSON") or _parse_json_line(lines, "PLAN_EXECUTOR_JSON")

    modified_paths = _collect_modified_paths(lines)
    before_data: Dict[str, Any] = {}
    after_data: Dict[str, Any] = {}
    diffs: List[Dict[str, Any]] = []

    for candidate in modified_paths:
        target = _resolve_candidate(candidate)
        bak = target.with_name(target.name + ".bak")
        before_content = bak.read_text(encoding="utf-8") if bak.exists() else None
        after_content = target.read_text(encoding="utf-8") if target.exists() else None
        if before_content is not None:
            before_data[target.as_posix()] = _try_load_json(before_content)
        if after_content is not None:
            after_data[target.as_posix()] = _try_load_json(after_content)
        if before_content is not None and after_content is not None:
            diff_text = _diff(before_content, after_content)
            if diff_text:
                diffs.append({"path": target.as_posix(), "diff": diff_text})

    return {
        "id": str(uuid.uuid4()),
        "task": task,
        "plan": plan,
        "before": before_data,
        "after": after_data,
        "diff": diffs,
        "rc": rc,
        "log": log_path.as_posix(),
    }


def build_dataset() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = _utc_timestamp()
    out_path = OUT_DIR / f"log_dataset-{ts}.jsonl"
    with out_path.open("w", encoding="utf-8") as handle:
        for log_path in _iter_logs():
            record = _extract_log_record(log_path)
            if not record:
                continue
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
            marker = OUT_DIR / f"processed-{log_path.name}.done"
            marker.write_text("done", encoding="utf-8")
    return out_path


def main() -> int:
    out_path = build_dataset()
    rows = sum(1 for _ in out_path.read_text(encoding="utf-8").splitlines() if _.strip())
    print(f"DATASET_WRITTEN path={out_path.as_posix()} rows={rows}")
    print(f"MASTER_DONE id={uuid.uuid4()} rc=0 out={out_path.as_posix()}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
