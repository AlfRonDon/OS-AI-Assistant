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

## FAISS corruption
- Rebuild the index from `retrieval/corpus/` using the standard indexing pipeline.
- Restore embeddings/payloads from `replays/pgvector_fallback.json` if Postgres is unavailable.
- Re-run indexing and a small search smoke test to confirm results.

## Wrong execute
- Abort the run immediately and avoid further state changes.
- Run `mock_os/undo` to restore the last checkpointed state.
- Check `telemetry/events.log` to find the planner output hash that led to the bad action.
- Restore the corresponding state snapshot if needed, and open an issue with details for follow-up.
