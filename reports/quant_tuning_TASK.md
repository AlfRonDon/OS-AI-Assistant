# Quant-Tuning Task (32GB+ host required)

## Inputs
- Base safetensors: `models/gpt-oss-20b/original/` (use `model.safetensors` already present; verify SHA before use).
- Converter: `scripts/convert_hf_to_gguf.py` (patched for gpt-oss-20b).
- Reference quant files for comparison: `models/All Models/gpt-oss-20b-q4_k_m.gguf` (stability) and `models/All Models/gpt-oss-20b-q8_0.gguf` (quality).

## Conversion (if a fresh f32 GGUF is needed)
```bash
python scripts/convert_hf_to_gguf.py \
  --model-dir models/gpt-oss-20b/original \
  --outfile models/gpt-oss-20b-f32.gguf
```

## Quant commands to run
- Target variants on the 32GB+ box: `q4_K_M` (baseline) and tuned `q4_K` / `q4_K_S` candidates for latency.
- Example using existing helper:
  ```bash
  pwsh -File scripts/run_quantize.ps1 -Input models/gpt-oss-20b-f32.gguf -Format q4_K_M
  pwsh -File scripts/run_quantize.ps1 -Input models/gpt-oss-20b-f32.gguf -Format q4_K_S
  ```
- Name outputs with timestamped suffix in `models/backups/`:
  - `models/backups/gpt-oss-20b-q4_K_M.<yyyymmdd_hhmmss>.gguf`
  - `models/backups/gpt-oss-20b-q4_K_S.<yyyymmdd_hhmmss>.gguf`

## Bench + validation
1. Warm bench on each produced GGUF:
   ```bash
   python bench/benchmark_model.py --model-path <GGUF> --warmups 3 --runs 10 --out bench/bench_results_full.json
   ```
2. Record results (copy JSON) into `reports/bench_results_full.json` and capture top metrics: p95 latency and peak RSS.
3. Load check:
   ```bash
   python scripts/check_model_load.py --model-path <GGUF> --timeout 120
   ```

## Expected uploads/artifacts
- Upload each candidate GGUF to the shared artifact bucket (or copy into `models/backups/` locally) alongside SHA256 lines in `reports/archive_safetensors_<ts>.txt`.
- Attach bench JSON and check_model_load output per file in `reports/quantize_q4_K_M.log` / new logs with suffixes.
- Provide a short README snippet with:
  - command used,
  - host RAM/CPU info,
  - observed `p95_ms` and `peak_rss_mb`,
  - recommendation (keep q4_K_M vs tuned variant).
