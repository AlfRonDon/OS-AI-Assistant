import json
import os
import time
from pathlib import Path
from typing import Any, Optional


REPORT_PATH = Path("reports/check_model_load_output.json")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _write_output(payload: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"WROTE {REPORT_PATH.as_posix()}")


def _import_dependencies(payload: dict[str, Any]):
    try:
        import psutil  # type: ignore
    except Exception as e:  # pragma: no cover - import failure path
        payload.update({"import_ok": False, "import_error": f"psutil: {e}"})
        return None, None

    try:
        from llama_cpp import Llama  # type: ignore
    except Exception as e:  # pragma: no cover - import failure path
        payload.update({"import_ok": False, "import_error": f"llama_cpp: {e}"})
        return psutil, None

    payload["import_ok"] = True
    return psutil, Llama


def main() -> int:
    model_path = Path(os.environ.get("GPT_OSS_MODEL_PATH", "models/gpt-oss-20b.gguf"))
    payload: dict[str, Any] = {
        "model_path": str(model_path),
        "import_ok": None,
        "import_error": None,
        "model_exists": model_path.exists(),
        "model_size_bytes": model_path.stat().st_size if model_path.exists() else 0,
    }

    psutil, Llama = _import_dependencies(payload)
    if not psutil or not Llama:
        _write_output(payload)
        return 0

    if not payload["model_exists"]:
        payload["run_error"] = f"MISSING_FILE: {model_path}"
        _write_output(payload)
        return 0

    try:
        process = psutil.Process(os.getpid())
        rss_before_mb: Optional[float] = process.memory_info().rss / (1024 * 1024)
    except Exception:
        process = None
        rss_before_mb = None

    # Safe loader: keep GPU layers disabled and avoid mlock to minimize host impact.
    llama_kwargs = {
        "model_path": str(model_path),
        "n_ctx": _env_int("LLAMA_CONTEXT", 512),
        "n_threads": _env_int("LLAMA_THREADS", os.cpu_count() or 1),
        "n_gpu_layers": _env_int("LLAMA_GPU_LAYERS", 0),
        "embedding": False,
        "logits_all": False,
        "use_mmap": True,
        "use_mlock": False,
        "verbose": False,
    }
    payload["loader_opts"] = {k: v for k, v in llama_kwargs.items() if k != "model_path"}

    print("Loading model with safe settings...", flush=True)
    t0 = time.time()
    try:
        llm = Llama(**llama_kwargs)
    except Exception as e:  # pragma: no cover - runtime path
        payload["run_error"] = f"Failed to load model: {e}"
        _write_output(payload)
        return 0
    t1 = time.time()

    response_preview = None
    try:
        resp = llm("Test.", max_tokens=6, temperature=0, stop=["</s>"])
        response_preview = str(resp)[:500]
    except Exception as e:  # pragma: no cover - runtime path
        payload["run_error"] = f"Inference error: {e}"
        t2 = time.time()
    else:
        t2 = time.time()

    rss_after_mb = None
    if process is not None:
        try:
            rss_after_mb = process.memory_info().rss / (1024 * 1024)
        except Exception:
            rss_after_mb = None

    payload.update(
        {
            "load_time_s": round(t1 - t0, 4),
            "gen_time_s": round(t2 - t1, 4),
        }
    )
    if rss_before_mb is not None:
        payload["rss_before_mb"] = round(rss_before_mb, 2)
    if rss_after_mb is not None:
        payload["rss_after_mb"] = round(rss_after_mb, 2)
    if response_preview is not None:
        payload["response_preview"] = response_preview

    _write_output(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
