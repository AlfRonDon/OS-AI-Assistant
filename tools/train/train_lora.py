from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.train.common import REPORTS_DIR, SEED, backup_file, iso_timestamp, log_line, utc_timestamp, write_json  # noqa: E402

MODELS_DIR = Path("models")


def _load_dataset(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _simulate_lora_training(batch: int, epochs: int, lora_r: int, qlora: bool, log_path: Path) -> Dict[str, Any]:
    """
    Run a tiny deterministic training loop to mimic adapter updates when GPU + torch are available.
    """
    try:
        import torch
    except Exception as exc:
        log_line(log_path, f"SIM_TRAIN torch_unavailable {exc}")
        return {"run_type": "mock", "reason": "torch unavailable"}

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device != "cuda":
        log_line(log_path, "SIM_TRAIN no_cuda_mock")
        return {"run_type": "mock", "reason": "cuda not available"}

    torch.manual_seed(SEED)
    hidden = max(8, lora_r * 2)
    model = torch.nn.Sequential(
        torch.nn.Linear(hidden, hidden, bias=False),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden, hidden, bias=False),
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    total_steps = max(1, epochs) * max(1, batch)
    start = time.time()
    for step in range(total_steps):
        if time.time() - start > 60:  # hard safety stop
            log_line(log_path, "SIM_TRAIN timeout_hit")
            break
        optimizer.zero_grad()
        data = torch.randn(batch, hidden, device=device)
        target = torch.zeros_like(data)
        loss = torch.nn.functional.mse_loss(model(data), target)
        loss.backward()
        optimizer.step()
    return {
        "run_type": "simulated",
        "device": device,
        "steps": total_steps,
        "qlora": qlora,
        "final_loss": float(loss.detach().cpu().item()),
    }


def _write_mock_artifact(out_path: Path, reason: str, log_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"mock": True, "reason": reason, "generated_at": iso_timestamp()}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log_line(log_path, f"MOCK_ARTIFACT {reason} path={out_path.as_posix()}")


def train(dataset_path: Path, output_path: Path, epochs: int, batch: int, lora_r: int, qlora: bool, log_path: Path, time_limit_minutes: int = 15) -> Tuple[int, Path, Path]:
    random.seed(SEED)
    start_time = time.time()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    backup_file(output_path, log_path)
    metrics_path = REPORTS_DIR / f"train-metrics-{utc_timestamp()}.json"

    rows = _load_dataset(dataset_path)
    log_line(log_path, f"TRAIN_START dataset={dataset_path.as_posix()} rows={len(rows)} epochs={epochs} batch={batch} lora_r={lora_r} qlora={qlora}")
    metrics: Dict[str, Any] = {
        "dataset": dataset_path.as_posix(),
        "rows": len(rows),
        "epochs": epochs,
        "batch": batch,
        "lora_r": lora_r,
        "qlora": qlora,
        "seed": SEED,
        "started_at": iso_timestamp(),
    }

    sim_result = _simulate_lora_training(batch=batch, epochs=epochs, lora_r=lora_r, qlora=qlora, log_path=log_path)
    metrics.update(sim_result)
    duration = time.time() - start_time
    metrics["duration_sec"] = duration
    if duration > time_limit_minutes * 60 or metrics.get("run_type") == "mock":
        _write_mock_artifact(output_path, metrics.get("reason", "timeboxed"), log_path)
    else:
        output_path.write_text(json.dumps({"weights": sim_result, "generated_at": iso_timestamp()}), encoding="utf-8")
        log_line(log_path, f"MODEL_WRITTEN path={output_path.as_posix()}")

    write_json(metrics_path, metrics)
    log_line(log_path, f"TRAIN_COMPLETE duration={duration:.2f}s run_type={metrics.get('run_type')}")
    return 0, output_path, metrics_path


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Minimal LoRA/QLoRA trainer stub with mock fallback.")
    parser.add_argument("--dataset", required=True, help="Path to training dataset JSONL.")
    parser.add_argument("--output", help="Output model path (default models/finetuned-<ts>.gguf)")
    parser.add_argument("--epochs", type=int, default=1, help="Number of epochs for simulated training.")
    parser.add_argument("--batch", type=int, default=4, help="Batch size for simulated training.")
    parser.add_argument("--lora-r", type=int, default=8, help="LoRA rank.")
    parser.add_argument("--qlora", action="store_true", help="Enable QLoRA mode (metadata only).")
    args = parser.parse_args(argv)

    ts = utc_timestamp()
    log_path = REPORTS_DIR / f"train-{ts}.log"
    config_path = REPORTS_DIR / f"train-config-{ts}.json"
    dataset_path = Path(args.dataset)
    output_path = Path(args.output) if args.output else MODELS_DIR / f"finetuned-{ts}.gguf"

    config = {
        "dataset": dataset_path.as_posix(),
        "output": output_path.as_posix(),
        "epochs": args.epochs,
        "batch": args.batch,
        "lora_r": args.lora_r,
        "qlora": args.qlora,
        "seed": SEED,
        "env": {"CI": os.getenv("CI", ""), "CUDA_VISIBLE_DEVICES": os.getenv("CUDA_VISIBLE_DEVICES", "")},
    }
    write_json(config_path, config)

    rc, _, metrics_path = train(dataset_path=dataset_path, output_path=output_path, epochs=args.epochs, batch=args.batch, lora_r=args.lora_r, qlora=args.qlora, log_path=log_path)
    print(f"TRAIN_SUMMARY rc={rc} model={output_path.as_posix()} metrics={metrics_path.as_posix()}")
    print(f"MASTER_DONE id={uuid.uuid4()} rc={rc} out={log_path.as_posix()}")
    return rc


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
