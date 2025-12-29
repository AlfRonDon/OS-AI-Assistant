#!/usr/bin/env python
import argparse
import datetime
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List

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


def _write_atomic_json(path: Path, payload: Dict[str, Any]) -> None:
    _write_atomic_text(path, json.dumps(payload, indent=2, sort_keys=True))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for raw in path.read_text(encoding='utf-8').splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rows.append(json.loads(raw))
        except Exception:
            continue
    return rows


def _compute_metrics(dataset: List[Dict[str, Any]], preds: List[Dict[str, Any]]) -> Dict[str, Any]:
    pred_by_id = {row.get('id'): row for row in preds if row.get('id') is not None}
    total = len(dataset)
    if total == 0:
        return {
            'planner_fidelity_pct': 100.0,
            'patch_exact_pct': 100.0,
            'exec_success_pct': 100.0,
            'planner_matches': 0,
            'patch_matches': 0,
            'exec_matches': 0,
            'total': 0,
        }

    planner_matches = 0
    patch_matches = 0
    exec_matches = 0

    for row in dataset:
        pred = pred_by_id.get(row.get('id'))
        if pred is None:
            continue
        if pred.get('plan') == row.get('plan'):
            planner_matches += 1
        if pred.get('post_files', {}) == row.get('post_files', {}):
            patch_matches += 1
        if int(pred.get('exec_rc', 1)) == 0:
            exec_matches += 1

    planner_fidelity_pct = planner_matches * 100.0 / total
    patch_exact_pct = patch_matches * 100.0 / total
    exec_success_pct = exec_matches * 100.0 / total

    return {
        'planner_fidelity_pct': planner_fidelity_pct,
        'patch_exact_pct': patch_exact_pct,
        'exec_success_pct': exec_success_pct,
        'planner_matches': planner_matches,
        'patch_matches': patch_matches,
        'exec_matches': exec_matches,
        'total': total,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Evaluate finetuned model outputs.')
    parser.add_argument('--dataset', required=True, help='Dataset JSONL used for evaluation.')
    parser.add_argument('--pred', required=True, help='Predictions JSONL to evaluate.')
    args = parser.parse_args()

    run_id = f"run_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    log_dir = Path('reports') / 'evaluate' / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / 'log.txt'
    meta_path = log_dir / 'meta.json'
    summary_path = log_dir / 'summary.json'

    eval_summary_dir = Path('reports') / f"eval_{run_id}"
    eval_summary_dir.mkdir(parents=True, exist_ok=True)
    eval_summary_path = eval_summary_dir / 'summary.json'

    rc = 0
    log_lines: List[str] = []

    dataset_path = Path(args.dataset)
    pred_path = Path(args.pred)

    dataset_rows = _read_jsonl(dataset_path)
    pred_rows = _read_jsonl(pred_path)

    log_lines.append(f"dataset={dataset_path.resolve()} rows={len(dataset_rows)}")
    log_lines.append(f"predictions={pred_path.resolve()} rows={len(pred_rows)}")

    metrics = _compute_metrics(dataset_rows, pred_rows)
    log_lines.append(f"planner_fidelity_pct={metrics['planner_fidelity_pct']:.2f}")
    log_lines.append(f"patch_exact_pct={metrics['patch_exact_pct']:.2f}")
    log_lines.append(f"exec_success_pct={metrics['exec_success_pct']:.2f}")

    threshold_failed = (
        metrics['planner_fidelity_pct'] < 85
        or metrics['patch_exact_pct'] < 75
        or metrics['exec_success_pct'] < 80
    )
    if threshold_failed:
        rc = 1
        log_lines.append('thresholds not met')

    summary = {
        'run_id': run_id,
        'dataset': str(dataset_path.resolve()),
        'pred': str(pred_path.resolve()),
        'metrics': metrics,
        'timestamp': datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
        'rc': rc,
    }

    _write_atomic_json(summary_path, summary)
    _write_atomic_json(eval_summary_path, summary)
    _write_atomic_text(log_path, "\n".join(log_lines) + ("\n" if log_lines else ""))
    _write_atomic_json(meta_path, summary)

    print(f"MASTER_DONE id={run_id} rc={rc} out={summary_path}")
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
