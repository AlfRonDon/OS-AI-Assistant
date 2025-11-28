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
