#!/usr/bin/env python
import argparse
import datetime
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

SEED = 1337


def _write_atomic_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copyfile(path, path.with_suffix(path.suffix + '.bak'))
    tmp_path = path.with_suffix(path.suffix + '.tmp')
    with tmp_path.open('w', encoding='utf-8') as handle:
        handle.write(text)
    os.replace(tmp_path, path)


def _sha256_json(obj: Dict[str, Any]) -> str:
    serialized = json.dumps(obj, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def _ensure_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _ensure_files_map(value: Any) -> Dict[str, str]:
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    return {}


def example_to_line(meta: Dict[str, Any], run_dir: str) -> Dict[str, Any]:
    input_prompt = meta.get('input_prompt', '')
    plan = _ensure_dict(meta.get('plan', {}))
    pre_files = _ensure_files_map(meta.get('pre_files', {}))
    post_files = _ensure_files_map(meta.get('post_files', {}))
    exec_rc = int(meta.get('exec_rc', 0))
    exec_log = str(meta.get('exec_log', ''))
    labels = _ensure_dict(meta.get('labels', {}))
    if 'task_type' not in labels:
        labels['task_type'] = str(meta.get('task_type', 'unknown'))
    timestamp = meta.get('timestamp') or datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
    source = str(run_dir)

    line_id = _sha256_json({
        'input_prompt': input_prompt,
        'plan': plan,
        'pre_files': pre_files,
    })

    return {
        'id': line_id,
        'timestamp': timestamp,
        'source': source,
        'input_prompt': input_prompt,
        'plan': plan,
        'pre_files': pre_files,
        'post_files': post_files,
        'exec_rc': exec_rc,
        'exec_log': exec_log,
        'labels': labels,
    }


def _collect_runs(runs_dir: Path) -> List[Path]:
    if not runs_dir.exists():
        return []
    return [p for p in sorted(runs_dir.iterdir()) if p.is_dir() and p.name.startswith('run_')]


def _build_dataset(runs_dir: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    dataset: List[Dict[str, Any]] = []
    log_lines: List[str] = []
    for run_path in _collect_runs(runs_dir):
        meta_path = run_path / 'meta.json'
        if not meta_path.exists():
            log_lines.append(f"{run_path.name}: skipped (missing meta.json)")
            continue
        try:
            with meta_path.open('r', encoding='utf-8') as handle:
                meta = json.load(handle)
        except Exception as exc:
            log_lines.append(f"{run_path.name}: skipped (meta.json error: {exc})")
            continue
        line = example_to_line(meta, str(run_path))
        dataset.append(line)
        log_lines.append(f"{run_path.name}: processed")
    return dataset, log_lines


def _write_jsonl(path: Path, examples: List[Dict[str, Any]]) -> None:
    lines = [json.dumps(example, sort_keys=True) for example in examples]
    payload = "\n".join(lines)
    if payload:
        payload += "\n"
    _write_atomic_text(path, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate fine-tuning dataset from run artifacts.')
    parser.add_argument('--runs-dir', required=True, help='Directory containing run_* folders with meta.json files.')
    parser.add_argument('--out', required=True, help='Output JSONL path for aggregated dataset.')
    args = parser.parse_args()

    run_id = f"run_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    log_dir = Path('reports') / 'generate_dataset' / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / 'log.txt'
    meta_path = log_dir / 'meta.json'

    runs_dir = Path(args.runs_dir)
    out_path = Path(args.out)
    rc = 0

    dataset: List[Dict[str, Any]] = []
    log_lines: List[str] = [f"runs_dir={runs_dir.resolve()}"]
    try:
        dataset, dataset_logs = _build_dataset(runs_dir)
        log_lines.extend(dataset_logs)
    except Exception as exc:
        rc = 1
        log_lines.append(f"fatal: {exc}")

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _write_jsonl(out_path, dataset)
        log_lines.append(f"output={out_path.resolve()}")
        log_lines.append(f"records={len(dataset)}")
    except Exception as exc:
        rc = 1
        log_lines.append(f"write_failed: {exc}")

    meta_doc = {
        'run_id': run_id,
        'runs_dir': str(runs_dir.resolve()),
        'out': str(out_path.resolve()),
        'records': len(dataset),
        'timestamp': datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
        'rc': rc,
    }

    _write_atomic_text(log_path, "\n".join(log_lines) + ("\n" if log_lines else ""))
    _write_atomic_text(meta_path, json.dumps(meta_doc, indent=2, sort_keys=True))

    print(f"MASTER_DONE id={run_id} rc={rc} out={log_path}")
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
