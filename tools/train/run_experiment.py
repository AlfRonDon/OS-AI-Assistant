from __future__ import annotations

import argparse
import tarfile
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.train import evaluate as eval_module  # noqa: E402
from tools.train import generate_dataset, train_lora  # noqa: E402
from tools.train.common import ARCHIVES_DIR, REPORTS_DIR, log_line, utc_timestamp, write_json, backup_file  # noqa: E402


def _archive(paths: List[Path], archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as tar:
        for path in paths:
            if path and path.exists():
                tar.add(path, arcname=path.name)


def _write_autofix_summary(log_path: Path, summary: Dict[str, Any]) -> Path:
    autofix_path = REPORTS_DIR / "autofix_summary.json"
    backup_file(autofix_path, log_path)
    write_json(autofix_path, summary)
    return autofix_path


def run_experiment(
    output_path: Path | None = None,
    epochs: int = 1,
    batch: int = 4,
    lora_r: int = 8,
    qlora: bool = False,
) -> Tuple[int, Dict[str, Any], Path]:
    ts = utc_timestamp()
    finetune_log = REPORTS_DIR / f"finetune-{ts}.log"
    log_line(finetune_log, "EXPERIMENT_START")

    dataset_path, rows, skip_log, ds_stats = generate_dataset.build_dataset(log_path=finetune_log)
    log_line(finetune_log, f"DATASET_DONE path={dataset_path.as_posix()} rows={rows}")
    if rows < 5:
        triage_path = REPORTS_DIR / f"finetune-triage-{ts}.txt"
        triage_path.write_text(f"Insufficient examples: {rows}", encoding="utf-8")
        log_line(finetune_log, f"TRIAGE insufficient_examples rows={rows}")
        summary = {"dataset": dataset_path.as_posix(), "rows": rows, "triage": triage_path.as_posix()}
        print(f"MASTER_DONE id={uuid.uuid4()} rc=1 out={finetune_log.as_posix()}")
        return 1, summary, finetune_log

    model_out = output_path or Path("models") / f"finetuned-{ts}.gguf"
    train_log = REPORTS_DIR / f"train-{ts}.log"
    train_config = REPORTS_DIR / f"train-config-{ts}.json"
    train_config_data = {
        "dataset": dataset_path.as_posix(),
        "output": model_out.as_posix(),
        "epochs": epochs,
        "batch": batch,
        "lora_r": lora_r,
        "qlora": qlora,
    }
    write_json(train_config, train_config_data)

    train_rc, model_path, metrics_path = train_lora.train(
        dataset_path=dataset_path,
        output_path=model_out,
        epochs=epochs,
        batch=batch,
        lora_r=lora_r,
        qlora=qlora,
        log_path=train_log,
    )
    log_line(finetune_log, f"TRAIN_DONE rc={train_rc} model={model_path.as_posix()}")

    eval_rc, eval_json, eval_md, eval_summary = eval_module.evaluate(dataset_path, log_path=finetune_log)
    log_line(finetune_log, f"EVAL_DONE rc={eval_rc} strict={eval_summary.get('strict_match_rate')}")

    exp_summary_path = REPORTS_DIR / f"exp-summary-{ts}.json"
    summary = {
        "dataset": dataset_path.as_posix(),
        "rows": rows,
        "dataset_stats": ds_stats,
        "skip_log": skip_log.as_posix(),
        "model": model_path.as_posix(),
        "train_log": train_log.as_posix(),
        "train_config": train_config.as_posix(),
        "train_metrics": metrics_path.as_posix(),
        "eval_json": eval_json.as_posix(),
        "eval_md": eval_md.as_posix(),
        "eval": eval_summary,
    }
    write_json(exp_summary_path, summary)

    archive_path = ARCHIVES_DIR / f"exp-{ts}.tar.gz"
    _archive(
        [
            dataset_path,
            skip_log,
            train_log,
            train_config,
            metrics_path,
            eval_json,
            eval_md,
            exp_summary_path,
            finetune_log,
        ],
        archive_path,
    )
    log_line(finetune_log, f"ARCHIVED path={archive_path.as_posix()}")

    autofix_summary = {
        "applied": [
            {
                "id": str(uuid.uuid4()),
                "change": "finetune pipeline experiment",
                "timestamp": ts,
                "details": {"dataset": dataset_path.as_posix(), "model": model_path.as_posix()},
            }
        ],
        "proposed": [],
    }
    _write_autofix_summary(finetune_log, autofix_summary)

    rc = 0 if train_rc == 0 and eval_rc == 0 else 1
    log_line(finetune_log, f"EXPERIMENT_DONE rc={rc}")
    print(f"MASTER_DONE id={uuid.uuid4()} rc={rc} out={finetune_log.as_posix()}")
    return rc, summary, finetune_log


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run full finetune pipeline: dataset -> train -> evaluate.")
    parser.add_argument("--output", help="Optional model output path.")
    parser.add_argument("--epochs", type=int, default=1, help="Epochs for training stub.")
    parser.add_argument("--batch", type=int, default=4, help="Batch size for training stub.")
    parser.add_argument("--lora-r", type=int, default=8, help="LoRA rank for training stub.")
    parser.add_argument("--qlora", action="store_true", help="Toggle QLoRA metadata mode.")
    args = parser.parse_args(argv)
    out_path = Path(args.output) if args.output else None
    rc, _, _ = run_experiment(output_path=out_path, epochs=args.epochs, batch=args.batch, lora_r=args.lora_r, qlora=args.qlora)
    return rc


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
