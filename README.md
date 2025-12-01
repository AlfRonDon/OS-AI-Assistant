# OS AI Assistant

Local-first LLM workstation for the `gpt-oss-20b` model with tooling to quantize, bench, and operate a fallback planner flow.

## What this repo contains
- **Model ops**: scripts under `scripts/` and `quant_tuning/` for converting HF safetensors to GGUF, quantizing to q4/q8, and running benches (see `RUNBOOK.md` for detailed steps).
- **Planner & executor**: logic under `planner/`, `services/`, and `executor/` to orchestrate local runs with optional remote planner fallback; operational details live in `ops/FALLBACK_README.md`.
- **Benchmarks & reports**: JSON/CSV artifacts in `bench/` plus example outputs in `reports/` showing expected metrics and diagnostics.
- **Automation**: GitHub Actions workflows under `.github/workflows/` and helper PowerShell/Bash scripts for CI and packaging.

## Quick start (dev box)
1. Create an environment: `python -m venv .venv && .venv/Scripts/Activate.ps1` (PowerShell) or `source .venv/bin/activate` (bash).
2. Install deps: `pip install -r requirements.txt` (and `-r requirements-dev.txt` for tests).
3. Prepare a model: follow `RUNBOOK.md` to convert HF weights and run `scripts/run_quantize.{ps1,sh}` for q4/q8 variants. Place the chosen `.gguf` at `models/gpt-oss-20b.gguf` (models are git-ignored).
4. Bench locally: `python bench/benchmark_model.py --model-path models/gpt-oss-20b.gguf --warmups 1 --runs 3`.
5. Run planner smoke: `python scripts/run_obedience_pack.py` or the PowerShell equivalents in `scripts/`.

## Ops notes
- The fallback procedure and autoselect policy are documented in `ops/FALLBACK_README.md`.
- Model binaries and large artifacts live under `models/` and are intentionally ignored by Git; fetch or generate them locally before running.
- For production-ish runs on Windows, start with the service wrappers in `scripts/watchdog_service_wrapper.ps1` and follow `RUNBOOK_FINAL.md` for operational guardrails.
