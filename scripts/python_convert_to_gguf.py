"""Attempt HF -> GGUF conversion via pure Python.

This script keeps all stdout/stderr quiet; progress is written to
reports/python_convert_to_gguf.log. It will try to import the
llama_cpp.convert_hf_to_gguf helper and run it if present. If the
converter is missing, a clear log entry is written and the script exits
without raising.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


MODEL_DIR = Path("models/gpt-oss-20b/original")
GGUF_OUT = Path("models/gpt-oss-20b.gguf")
LOG_PATH = Path("reports/python_convert_to_gguf.log")


def _setup_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("python_convert_to_gguf")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s\t%(levelname)s\t%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    logger.info("Log initialized at %s", datetime.utcnow().isoformat() + "Z")
    return logger


def _ensure_inputs(logger: logging.Logger) -> bool:
    required = [
        MODEL_DIR / "model.safetensors",
        MODEL_DIR / "config.json",
        MODEL_DIR / "dtypes.json",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        logger.error("Missing required model artifacts: %s", missing)
        return False
    logger.info("All required input files located.")
    return True


def _load_transformers(logger: logging.Logger) -> Tuple[Optional[object], Optional[object]]:
    # Quiet down noisy components to avoid console output.
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("BITSANDBYTES_NOWELCOME", "1")

    try:
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
    except Exception as exc:  # pragma: no cover - import failure path
        logger.error("Transformers import failed: %s", exc)
        return None, None
    try:
        from accelerate import init_empty_weights  # type: ignore
    except Exception:
        init_empty_weights = None

    tokenizer = None
    model = None

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            MODEL_DIR,
            trust_remote_code=True,
            use_fast=True,
            local_files_only=True,
        )
        logger.info("Tokenizer loaded successfully.")
    except Exception as exc:  # pragma: no cover - runtime path
        logger.exception("Tokenizer load failed", exc_info=exc)

    try:
        config = AutoConfig.from_pretrained(
            MODEL_DIR,
            trust_remote_code=True,
            local_files_only=True,
        )
        logger.info("Config loaded successfully.")
    except Exception as exc:  # pragma: no cover - runtime path
        logger.exception("Config load failed", exc_info=exc)
        return None, tokenizer

    if init_empty_weights:
        try:
            with init_empty_weights():
                model = AutoModelForCausalLM.from_config(
                    config,
                    trust_remote_code=True,
                )
            logger.info("Model instantiated with empty weights for structural validation.")
        except Exception as exc:  # pragma: no cover - runtime path
            logger.warning("Model instantiation skipped: %s", exc)
    else:
        logger.warning("accelerate.init_empty_weights unavailable; skipping model instantiation to avoid large allocations.")

    return model, tokenizer


def _converter_available(logger: logging.Logger) -> bool:
    try:
        import importlib

        importlib.import_module("llama_cpp.convert_hf_to_gguf")
    except Exception as exc:  # pragma: no cover - runtime path
        logger.error("llama_cpp.convert_hf_to_gguf not available: %s", exc)
        return False

    logger.info("llama_cpp.convert_hf_to_gguf module detected.")
    return True


def _run_converter(logger: logging.Logger) -> bool:
    cmd = [
        sys.executable,
        "-m",
        "llama_cpp.convert_hf_to_gguf",
        str(MODEL_DIR),
        "--outfile",
        str(GGUF_OUT),
    ]
    logger.info("Executing converter command: %s", json.dumps(cmd))
    env = os.environ.copy()
    env.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    env.setdefault("TRANSFORMERS_VERBOSITY", "error")

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.stdout:
        logger.info("converter stdout:\n%s", result.stdout.rstrip())
    if result.stderr:
        logger.info("converter stderr:\n%s", result.stderr.rstrip())
    if result.returncode != 0:
        logger.error("Converter exited with code %s", result.returncode)
        return False

    logger.info("Converter completed with exit code 0.")
    return True


def _log_output_file(logger: logging.Logger) -> None:
    gguf_exists = GGUF_OUT.exists()
    size = GGUF_OUT.stat().st_size if gguf_exists else 0
    logger.info("GGUF exists: %s", gguf_exists)
    if gguf_exists:
        logger.info("GGUF size (bytes): %s", size)


def main() -> int:
    logger = _setup_logging()
    logger.info("Starting Python-based GGUF conversion attempt.")
    logger.info("Model directory: %s", MODEL_DIR)
    logger.info("Output path: %s", GGUF_OUT)

    if not _ensure_inputs(logger):
        _log_output_file(logger)
        return 0

    _load_transformers(logger)

    if not _converter_available(logger):
        logger.info("Converter not available; exiting without error.")
        _log_output_file(logger)
        return 0

    conversion_ok = _run_converter(logger)
    logger.info("Conversion success flag: %s", conversion_ok)
    _log_output_file(logger)
    logger.info("Conversion run finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
