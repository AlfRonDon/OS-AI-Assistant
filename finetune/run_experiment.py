#!/usr/bin/env python
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


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


def _run_cmd(cmd: List[str], log_lines: List[str]) -> int:
    result = subprocess.run(cmd, capture_output=True, text=True)
    log_lines.append('$ ' + ' '.join(cmd))
    if result.stdout:
        log_lines.append('stdout: ' + result.stdout.strip())
    if result.stderr:
        log_lines.append('stderr: ' + result.stderr.strip())
    log_lines.append(f'rc={result.returncode}')
    return result.returncode


def _load_config(config_path: Path) -> Dict[str, Any]:
    if config_path.exists():
        try:
            with config_path.open('r', encoding='utf-8') as handle:
                return json.load(handle)
        except Exception:
            return {}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description='Run full fine-tuning experiment pipeline.')
    parser.add_argument('--runs-dir', default='reports', help='Directory containing run_* folders.')
    parser.add_argument('--dataset-out', default='data/train/dataset.jsonl', help='Aggregated dataset path.')
    parser.add_argument('--train-out', default='data/train/out', help='Directory for training artifacts.')
    parser.add_argument('--config', default='configs/lora_default.json', help='Config JSON with training defaults.')
    parser.add_argument('--smoke', action='store_true', help='Enable smoke mode for speed.')
    args = parser.parse_args()

    run_id = f"run_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    log_dir = Path('reports') / 'experiment' / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / 'log.txt'
    meta_path = log_dir / 'meta.json'

    log_lines: List[str] = []
    rc = 0

    dataset_out = Path(args.dataset_out)
    train_out = Path(args.train_out)
    config = _load_config(Path(args.config))
    log_lines.append(f"config_loaded={bool(config)} from {Path(args.config).resolve()}")

    dataset_out.parent.mkdir(parents=True, exist_ok=True)
    train_out.mkdir(parents=True, exist_ok=True)

    gen_cmd = [
        sys.executable,
        str(Path('finetune/scripts/generate_dataset.py')),
        '--runs-dir', str(Path(args.runs_dir)),
        '--out', str(dataset_out),
    ]
    rc_gen = _run_cmd(gen_cmd, log_lines)
    if rc_gen != 0:
        rc = 1

    train_cmd = [
        sys.executable,
        str(Path('finetune/train_lora.py')),
        '--dataset', str(dataset_out),
        '--out', str(train_out),
        '--epochs', str(config.get('epochs', 1)),
        '--batch', str(config.get('batch', 1)),
        '--lr', str(config.get('lr', 2e-4)),
        '--precision', str(config.get('precision', 'fp16')),
        '--seed', str(config.get('seed', 1337)),
    ]
    if args.smoke:
        train_cmd.append('--smoke')
    if config.get('resume'):
        train_cmd.extend(['--resume', str(config['resume'])])

    rc_train = None
    if rc == 0:
        rc_train = _run_cmd(train_cmd, log_lines)
        if rc_train != 0:
            rc = 1

    preds_path = train_out / 'preds.jsonl'
    eval_cmd = [
        sys.executable,
        str(Path('finetune/evaluate.py')),
        '--dataset', str(dataset_out),
        '--pred', str(preds_path),
    ]
    rc_eval = None
    if rc == 0:
        rc_eval = _run_cmd(eval_cmd, log_lines)
        if rc_eval != 0:
            rc = 1

    meta_doc = {
        'run_id': run_id,
        'runs_dir': str(Path(args.runs_dir).resolve()),
        'dataset_out': str(dataset_out.resolve()),
        'train_out': str(train_out.resolve()),
        'config': str(Path(args.config).resolve()),
        'rc': rc,
        'rc_generate': rc_gen,
        'rc_train': rc_train,
        'rc_eval': rc_eval,
        'timestamp': datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
        'smoke': bool(args.smoke),
    }

    _write_atomic_text(log_path, "\n".join(log_lines) + ("\n" if log_lines else ""))
    _write_atomic_json(meta_path, meta_doc)

    print(f"MASTER_DONE id={run_id} rc={rc} out={log_path}")
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
