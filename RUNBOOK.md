# RUNBOOK

## Planner outputs invalid JSON
- Check `reports/obedience_report.json` for recent failures.
- Re-run the specific prompt with extra debugging enabled (`python scripts/run_obedience_pack.py` or a focused harness) to reproduce.
- Inspect `planner/runner.log` or local console logs to see validation errors.
- If schema mismatch appears, add or adjust retrieval snippets or tighten the prompt until validation passes.
- To roll back a bad change quickly, use `git revert` on the offending commit.

## Model OOM
- Review `bench/bench_results.json` to confirm memory spikes.
- Reduce batch size or sequence length in the calling code and retry.
- Enable quantization and verify with `scripts/quantize_and_validate.sh`.
- If local hardware remains constrained, push workloads to a server fallback path.

## Quantize and bench GPT_OSS model
- Set the model path before running tools: `export GPT_OSS_MODEL_PATH=models/gpt-oss-20b.gguf` (bash) or `$env:GPT_OSS_MODEL_PATH="models/gpt-oss-20b.gguf"` (PowerShell).
- Quantize when a tool is available: `convert-gguf --input "$env:GPT_OSS_MODEL_PATH" --output models/gpt-oss-20b-q.gguf --format q4_0` (or `python -m llama_cpp.quantize --input "$env:GPT_OSS_MODEL_PATH" --output models/gpt-oss-20b-q.gguf --format q4_0`).
- Rerun the bench against the chosen file: `python bench/benchmark_model.py --model-path models/gpt-oss-20b-q.gguf --warmups 3 --runs 10` and confirm `bench/bench_results.json` reports nonzero `peak_rss`.

## FAISS corruption
- Rebuild the index from `retrieval/corpus/` using the standard indexing pipeline.
- Restore embeddings/payloads from `replays/pgvector_fallback.json` if Postgres is unavailable.
- Re-run indexing and a small search smoke test to confirm results.

## Wrong execute
- Abort the run immediately and avoid further state changes.
- Run `mock_os/undo` to restore the last checkpointed state.
- Check `telemetry/events.log` to find the planner output hash that led to the bad action.
- Restore the corresponding state snapshot if needed, and open an issue with details for follow-up.

## Model storage & cleanup
- Point archives to an external path with plenty of free space (e.g., `D:\model_archives\`); avoid filling the system drive.
- Copy and verify the original safetensors with `scripts/archive_model.ps1`; choose the symlink option to replace `models/gpt-oss-20b/original/model.safetensors` with a link pointing at the archived copy when you want the local footprint minimized.
- Manual symlink fallback: remove or move the original file, then run `New-Item -ItemType SymbolicLink -Path models/gpt-oss-20b/original/model.safetensors -Target <archived-path>`.
- Keep only the newest 3 backups in `models/backups/` using `scripts/rotate_backups.ps1` (double confirmation required before deletion).
- Compress routine logs with `scripts/cleanup_logs.ps1` (or `.sh` in WSL); archives land in `logs/archive/` and raw logs older than 90 days are cleared.
- Checklist: run `scripts/estimate_free_space.ps1`, pick an archive destination, run `scripts/free_space_dryrun.ps1`, archive the model, rotate backups, clean logs, and rerun the estimate to confirm reclaimed space.
