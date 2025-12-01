# RUNBOOK_FINAL - Edge Ops Snapshot (20251201_171735)

## Active Variant Snapshot
- Active file: `models/gpt-oss-20b.gguf` (22261895200 bytes).
- Known quant sizes: q4_K_M ≈ 15805119520 bytes, q8_0 ≈ 22261895200 bytes.
- Active assumption: **q8_0** (size match). q4_K_M fallback lives at `models/All Models/gpt-oss-20b-q4_k_m.gguf`.
- Validation: `python scripts/check_model_load.py --model-path models/gpt-oss-20b.gguf`.

## Swap/Revert (atomic moves)
- Switch to q4_K_M for stability:
  ```powershell
  $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
  Move-Item models/gpt-oss-20b.gguf "models/gpt-oss-20b.gguf.broken.$ts"
  Copy-Item "models/All Models/gpt-oss-20b-q4_k_m.gguf" models/gpt-oss-20b.gguf
  python scripts/check_model_load.py --model-path models/gpt-oss-20b.gguf
  ```
- Restore q8_0 after validation:
  ```powershell
  $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
  Move-Item models/gpt-oss-20b.gguf "models/gpt-oss-20b.gguf.broken.$ts"
  Copy-Item "models/All Models/gpt-oss-20b-q8_0.gguf" models/gpt-oss-20b.gguf
  python scripts/check_model_load.py --model-path models/gpt-oss-20b.gguf
  ```

## Watchdog Registration (exact command)
```powershell
Register-ScheduledTask -TaskName "EdgeOSWatchdog" -Action (New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument "-NoProfile -WindowStyle Hidden -File `\"C:\Users\alfre\OS AI Agent\scripts\watchdog_service_wrapper.ps1`\"") -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration ([TimeSpan]::MaxValue)) -RunLevel Highest -Force
```
- Run as Administrator. If registration succeeds, start via `Start-ScheduledTask -TaskName "EdgeOSWatchdog"` and tail `reports/watchdog.log` (last 30 lines saved to `reports/watchdog_postinstall.log` when applied).

## CI Flags & Thresholds
- CI status: `CI_OUT=CI_SKIPPED` (AUTO_CI_REMOTE unset). Recommend adding repo secret `CI_USE_REMOTE_MODEL=1` when `origin` and `gh` are available.
- Bench relaxation (if needed): set `bench/bench_thresholds.json` to `p95_ms=16000` and `rss_max_mb=5000` while keeping `obedience_pass_rate=1.0` (patch sample in `reports/bench_thresholds_patch.txt`).

## Quant-Tuning & Monitoring
- Quant-tuning plan: follow `reports/quant_tuning_TASK.md` (32GB+ host) and drop resulting `.gguf` plus SHA256 into `models/backups/`.
- Monitoring notifier: `ops/notify_slack.ps1` tails `reports/alerts.log`, posts to `$env:SLACK_WEBHOOK_URL`, and records last run at `reports/notify_slack_last.txt`; schedule via `reports/monitor_task_instructions.txt` (5-minute cadence, elevated).
- Autoselect reference: `scripts/autoselect_quant_variant.ps1` and `config/autoselect_policy.json`; dry-run using `AUTOSELECT_DRY_RUN=1` in CI.
