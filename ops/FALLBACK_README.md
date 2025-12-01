
# FALLBACK: active q4_K_M

Active variant set to **q4_K_M** on host to restore stability.

Reason:

* q8_0 produced unstable p95 (exceeded thresholds) on this hardware.
* q4_K_M reduces memory use at cost of latency.

Temporary policy:

* Keep q4_K_M as active until quant_tuning on a larger host produces a better hybrid variant (q4_KV / q4_K_M tuned).

* To revert: place the validated q8_0 file at models/gpt-oss-20b-q8_0.gguf, then run:
  Move-Item models/gpt-oss-20b.gguf models/gpt-oss-20b.gguf.broken.YYYYMMDD_HHMMSS
  Move-Item models/gpt-oss-20b-q8_0.gguf models/gpt-oss-20b.gguf
  python scripts/check_model_load.py --model-path models/gpt-oss-20b.gguf

* This file is committed for operational traceability.

