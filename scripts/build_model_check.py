import json
from pathlib import Path


def read(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    raw = p.read_bytes()
    for enc in ("utf-8", "utf-16", "utf-16le", "utf-16be", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def main() -> int:
    ls_output = read("reports/model_ls.txt")
    planner_text = read("reports/planner_smoke.txt").strip()
    check_text = read("reports/check_model_load.txt").strip()
    quantize_text = read("reports/quantize_check.txt").strip()

    file_path = Path("models/gpt-oss-20b.gguf")
    file_exists = file_path.exists()
    file_size_bytes = file_path.stat().st_size if file_exists else 0
    human_size = f"{file_size_bytes} bytes" if file_exists else "missing"

    planner_data = {
        "ran": bool(planner_text),
        "raw_output": planner_text,
        "runtime_ms": None,
        "used_entry": None,
        "success_guess": False,
    }
    parsed_planner = None
    if planner_text:
        try:
            parsed_planner = json.loads(planner_text)
        except Exception:
            parsed_planner = None
    if parsed_planner:
        planner_data.update(
            {
                "ran": True,
                "raw_output": planner_text,
                "runtime_ms": parsed_planner.get("runtime_ms"),
                "used_entry": parsed_planner.get("used_entry"),
                "success_guess": bool(parsed_planner.get("success_guess")),
            }
        )

    import_errors = None
    check_script_ran = bool(check_text)
    load_time_s = gen_time_s = rss_before_mb = rss_after_mb = None
    response_preview = None
    exit_code = None
    parsed_check = None
    if "IMPORT_ERROR" in check_text:
        import_errors = [line for line in check_text.splitlines() if "IMPORT_ERROR" in line]
        exit_code = 2
    if check_text:
        try:
            parsed_check = json.loads(check_text.splitlines()[-1])
        except Exception:
            parsed_check = None
    if parsed_check and isinstance(parsed_check, dict) and "load_time_s" in parsed_check:
        load_time_s = parsed_check.get("load_time_s")
        gen_time_s = parsed_check.get("gen_time_s")
        rss_before_mb = parsed_check.get("rss_before_mb")
        rss_after_mb = parsed_check.get("rss_after_mb")
        response_preview = parsed_check.get("response_preview")
        exit_code = 0 if exit_code is None else exit_code
    elif exit_code is None and "Failed to load model" in check_text:
        exit_code = 1
    elif exit_code is None and "MISSING_FILE" in check_text:
        exit_code = 3

    quantize_available = False
    quantize_cmd = None
    for line in quantize_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Directory"):
            continue
        lower = stripped.lower()
        looks_like_cmd = lower.startswith(("quantize", "convert-gguf")) or ".exe" in lower or ".bin" in lower
        if ("quantize" in lower or "convert-gguf" in lower) and looks_like_cmd:
            quantize_available = True
            quantize_cmd = stripped
            break

    model_file_stub = (not file_exists) or file_size_bytes < 200_000_000
    model_loaded_real = False
    if rss_after_mb is not None and rss_before_mb is not None:
        model_loaded_real = (rss_after_mb - rss_before_mb >= 500) or (rss_after_mb >= 500)

    recommendations = []
    if model_file_stub:
        recommendations.append("Replace models/gpt-oss-20b.gguf with a real gguf (size several GB).")
    if not quantize_available:
        recommendations.append("Install/build quantize tool (link: README/Runbook) or use remote inference.")
    if model_loaded_real:
        recommendations.append("Model appears loaded; re-run full obedience pack and bench under real model.")
    elif file_exists and not model_file_stub:
        recommendations.append("Model file present but load did not increase RSS; check llama-cpp-python compatibility or use alternative loader.")
    if exit_code not in (0, None) and not import_errors:
        recommendations.append("Model load could not be validated; check reports/check_model_load.txt for loader errors.")
    elif import_errors:
        recommendations.append("Model load could not be validated due to missing imports; ensure psutil and llama-cpp-python are installed.")

    data = {
        "model_path": str(file_path),
        "file_exists": file_exists,
        "file_size_bytes": file_size_bytes,
        "human_size": human_size,
        "planner_smoke": planner_data,
        "check_script_ran": check_script_ran,
        "import_errors": import_errors,
        "load_time_s": load_time_s,
        "gen_time_s": gen_time_s,
        "rss_before_mb": rss_before_mb,
        "rss_after_mb": rss_after_mb,
        "response_preview": response_preview,
        "exit_code": exit_code,
        "quantize_available": quantize_available,
        "quantize_cmd": quantize_cmd,
        "model_file_stub": model_file_stub,
        "model_loaded_real": model_loaded_real,
        "recommendations": recommendations,
        "model_ls_output": ls_output,
        "check_model_output": check_text,
        "quantize_output": quantize_text,
    }

    Path("reports/model_check.json").write_text(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
