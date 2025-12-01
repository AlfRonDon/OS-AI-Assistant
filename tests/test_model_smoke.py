import json
import os
import time
from pathlib import Path

import pytest

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency for diagnostics
    psutil = None


def _write_report(payload: dict) -> None:
    report_path = Path(__file__).resolve().parents[1] / "reports" / "tests" / "smoke_load.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2))


def test_gguf_loads():
    model_path = Path(__file__).resolve().parents[1] / "models" / "gpt-oss-20b.gguf"
    if not model_path.exists():
        pytest.skip("models/gpt-oss-20b.gguf missing; skipping smoke load.")
    if os.getenv("DISABLE_LOCAL_LLM", "").lower() in {"1", "true", "yes"}:
        pytest.skip("local LLM disabled via DISABLE_LOCAL_LLM; skipping heavy load.")

    try:
        from llama_cpp import Llama  # type: ignore
    except Exception as exc:  # pragma: no cover - import guard
        pytest.skip(f"llama_cpp unavailable: {exc}")

    payload: dict[str, object] = {"model_path": str(model_path)}
    process = psutil.Process(os.getpid()) if psutil else None
    if process:
        try:
            payload["rss_before_mb"] = round(process.memory_info().rss / (1024 * 1024), 2)
        except Exception:
            payload["rss_before_mb"] = None

    t0 = time.perf_counter()
    try:
        llm = Llama(model_path=str(model_path), n_ctx=32)
        t1 = time.perf_counter()

        response = llm("Hello", max_tokens=1, temperature=0)
        t2 = time.perf_counter()
    except Exception as exc:
        payload["error"] = str(exc)
        raise
    finally:
        if process:
            try:
                payload["rss_after_mb"] = round(process.memory_info().rss / (1024 * 1024), 2)
            except Exception:
                payload["rss_after_mb"] = None

        if "load_time_s" not in payload and "error" not in payload:
            payload["load_time_s"] = round(time.perf_counter() - t0, 4)
        _write_report(payload)

    payload["load_time_s"] = round(t1 - t0, 4)
    payload["gen_time_s"] = round(t2 - t1, 4)
    payload["response_preview"] = str(response)[:400]
    _write_report(payload)

    assert response, "llama_cpp returned empty response"
    choice = response.get("choices", [{}])[0]
    text = choice.get("text", "")
    assert isinstance(text, str)
    assert text.strip(), "model returned empty text"
