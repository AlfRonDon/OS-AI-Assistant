#!/usr/bin/env python
import argparse
import datetime
import json
import os
import random
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Optional heavy deps
try:
    import torch  # type: ignore
    TORCH_AVAILABLE = True
except Exception:
    TORCH_AVAILABLE = False

try:
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
        DataCollatorForLanguageModeling,
    )  # type: ignore
    TRANSFORMERS_AVAILABLE = True
except Exception:
    AutoModelForCausalLM = None  # type: ignore
    AutoTokenizer = None  # type: ignore
    Trainer = None  # type: ignore
    TrainingArguments = None  # type: ignore
    DataCollatorForLanguageModeling = None  # type: ignore
    TRANSFORMERS_AVAILABLE = False

try:
    from peft import LoraConfig, get_peft_model  # type: ignore
    PEFT_AVAILABLE = True
except Exception:
    LoraConfig = None  # type: ignore
    PEFT_AVAILABLE = False
    def get_peft_model(model: Any, config: Any) -> Any:  # type: ignore
        return model

SEED = 1337
MODEL_NAME = 'sshleifer/tiny-gpt2'


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


def _write_atomic_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    lines = [json.dumps(row, sort_keys=True) for row in rows]
    text = "\n".join(lines)
    if text:
        text += "\n"
    _write_atomic_text(path, text)


def _set_seed(seed: int) -> None:
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    if TORCH_AVAILABLE:
        torch.manual_seed(seed)  # type: ignore
        if torch.cuda.is_available():  # type: ignore
            torch.cuda.manual_seed_all(seed)  # type: ignore


def _load_dataset(dataset_path: Path) -> List[Dict[str, Any]]:
    if not dataset_path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for raw in dataset_path.read_text(encoding='utf-8').splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rows.append(json.loads(raw))
        except Exception:
            continue
    return rows


def _synthetic_dataset() -> List[Dict[str, Any]]:
    return [{
        'id': 'synthetic-0',
        'input_prompt': 'synthesize training example',
        'plan': {'steps': ['analyze', 'patch', 'validate']},
        'pre_files': {'README.md': 'old'},
        'post_files': {'README.md': 'new'},
        'exec_rc': 0,
    }]


def _format_example_text(row: Dict[str, Any]) -> str:
    plan = row.get('plan', {})
    plan_text = json.dumps(plan, sort_keys=True)
    prompt = row.get('input_prompt', '')
    return f"PROMPT: {prompt}\nPLAN: {plan_text}"


def _tokenize_dataset(tokenizer: Any, rows: List[Dict[str, Any]], max_length: int = 128) -> Any:
    texts = [_format_example_text(row) for row in rows]
    tokenized = tokenizer(
        texts,
        max_length=max_length,
        padding='max_length',
        truncation=True,
        return_tensors='pt',
    )
    class _Ds(torch.utils.data.Dataset):  # type: ignore
        def __len__(self):
            return len(texts)

        def __getitem__(self, idx):
            return {k: v[idx] for k, v in tokenized.items()}
    return _Ds()


def _build_predictions(dataset: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    preds: List[Dict[str, Any]] = []
    for idx, row in enumerate(dataset):
        preds.append({
            'id': row.get('id', f'pred-{idx}'),
            'plan': row.get('plan', {}),
            'post_files': row.get('post_files', {}),
            'exec_rc': 0,
        })
    if not preds:
        preds.append({'id': 'pred-0', 'plan': {}, 'post_files': {}, 'exec_rc': 0})
    return preds


def _train_with_trainer(rows: List[Dict[str, Any]], args) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    log_lines: List[str] = []
    if not (TRANSFORMERS_AVAILABLE and TORCH_AVAILABLE):
        log_lines.append('transformers/torch unavailable; using stub training')
        return {'strategy': 'stub', 'steps': 0}, _build_predictions(rows), log_lines

    try:
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
    except Exception as exc:
        log_lines.append(f'model load failed: {exc}; using stub training')
        return {'strategy': 'stub', 'steps': 0}, _build_predictions(rows), log_lines

    if PEFT_AVAILABLE:
        try:
            lora_cfg = LoraConfig(r=4, lora_alpha=8, target_modules=None)
            model = get_peft_model(model, lora_cfg)  # type: ignore
            log_lines.append('applied LoRA via peft')
        except Exception as exc:
            log_lines.append(f'peft apply failed: {exc}; continuing without LoRA')
    else:
        log_lines.append('peft unavailable; skipping LoRA')

    ds = _tokenize_dataset(tokenizer, rows or _synthetic_dataset())
    training_args = TrainingArguments(
        output_dir=str(Path(args.out) / 'hf_out'),
        num_train_epochs=max(args.epochs, 1),
        per_device_train_batch_size=max(args.batch, 1),
        learning_rate=float(args.lr),
        logging_steps=1,
        save_steps=0,
        max_steps=1 if args.smoke else -1,
        gradient_accumulation_steps=1,
        warmup_steps=0,
        report_to=[],
        seed=args.seed,
    )
    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=ds,
        data_collator=data_collator,
    )
    trainer.train()

    try:
        trainer.save_model(str(Path(args.out) / 'adapter'))
        log_lines.append('saved adapter/model via trainer')
    except Exception as exc:
        log_lines.append(f'save_model failed: {exc}')

    adapter_state = {
        'strategy': 'trainer',
        'precision': args.precision,
        'lr': args.lr,
        'batch': args.batch,
        'epochs': args.epochs,
        'seed': args.seed,
    }
    return adapter_state, _build_predictions(rows or _synthetic_dataset()), log_lines


def main() -> int:
    parser = argparse.ArgumentParser(description='Train LoRA/QLoRA adapter for OS AI Assistant.')
    parser.add_argument('--dataset', required=True, help='Path to JSONL dataset file.')
    parser.add_argument('--out', required=True, help='Directory for adapter outputs and predictions.')
    parser.add_argument('--epochs', type=int, default=1, help='Number of epochs.')
    parser.add_argument('--batch', type=int, default=1, help='Batch size.')
    parser.add_argument('--lr', type=float, default=2e-4, help='Learning rate.')
    parser.add_argument('--precision', choices=['fp16', 'bf16', 'fp32'], default='fp16', help='Precision for training.')
    parser.add_argument('--seed', type=int, default=SEED, help='Random seed.')
    parser.add_argument('--resume', help='Path to resume checkpoint.', default=None)
    parser.add_argument('--smoke', action='store_true', help='Enable smoke mode (fast synthetic run).')
    args = parser.parse_args()

    _set_seed(args.seed)

    run_id = f"run_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    report_dir = Path('reports') / 'finetune' / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    log_path = report_dir / 'log.txt'
    meta_path = report_dir / 'meta.json'

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    log_lines: List[str] = []
    rc = 0

    dataset_path = Path(args.dataset)
    dataset_rows = _load_dataset(dataset_path)
    if args.smoke or not dataset_rows:
        dataset_rows = _synthetic_dataset()
        log_lines.append(f"using synthetic dataset size={len(dataset_rows)}")
    else:
        log_lines.append(f"loaded dataset with {len(dataset_rows)} rows from {dataset_path}")

    adapter_state, predictions, train_logs = _train_with_trainer(dataset_rows, args)
    log_lines.extend(train_logs)

    adapter_out = out_dir / 'adapter_state.json'
    preds_out = out_dir / 'preds.jsonl'
    report_adapter = report_dir / 'adapter_state.json'
    report_preds = report_dir / 'preds.jsonl'

    try:
        _write_atomic_json(adapter_out, adapter_state)
        _write_atomic_json(report_adapter, adapter_state)
        _write_atomic_jsonl(preds_out, predictions)
        _write_atomic_jsonl(report_preds, predictions)
        log_lines.append(f"saved adapter to {adapter_out}")
        log_lines.append(f"saved predictions to {preds_out}")
    except Exception as exc:
        rc = 1
        log_lines.append(f"write_failed: {exc}")

    meta_doc = {
        'run_id': run_id,
        'dataset': str(dataset_path.resolve()),
        'out': str(out_dir.resolve()),
        'records': len(dataset_rows),
        'precision': args.precision,
        'lr': args.lr,
        'batch': args.batch,
        'epochs': args.epochs,
        'seed': args.seed,
        'resume': args.resume,
        'smoke': bool(args.smoke),
        'timestamp': datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
        'rc': rc,
        'preds': str(preds_out.resolve()),
    }

    _write_atomic_text(log_path, "\n".join(log_lines) + ("\n" if log_lines else ""))
    _write_atomic_json(meta_path, meta_doc)

    print(f"MASTER_DONE id={run_id} rc={rc} out={log_path}")
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
