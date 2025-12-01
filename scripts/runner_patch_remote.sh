#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${ROOT}/planner/runner.py"
REPORT="${ROOT}/reports/runner_remote_patch.diff"

if [[ ! -f "${TARGET}" ]]; then
  echo "error: ${TARGET} not found" >&2
  exit 1
fi

timestamp="$(date +%Y%m%d%H%M%S)"
backup="${TARGET}.bak.${timestamp}"

cp "${TARGET}" "${backup}"

python - <<'PY' "${TARGET}"
from __future__ import annotations

import sys
from pathlib import Path

target = Path(sys.argv[1])
text = target.read_text(encoding="utf-8")

start = text.find("def run_planner(")
end = text.find("def run_planner_with_preview")
if start == -1 or end == -1:
    raise SystemExit("run_planner boundaries not found; aborting patch")

replacement = '''def run_planner(retrieval_snippets: List[str], state_snapshot: Dict[str, Any], user_query: str):
    prompt = build_prompt(retrieval_snippets, state_snapshot, user_query)
    use_remote = bool((os.getenv("USE_REMOTE_MODEL") or "").strip())
    model_plan = None
    used_fallback = False
    raw_plan: Dict[str, Any] = {}

    if use_remote:
        try:
            from planner import remote_adapter

            remote_plan = remote_adapter.call_remote_planner(retrieval_snippets, state_snapshot, user_query)
            if remote_plan and not (isinstance(remote_plan, dict) and remote_plan.get("error")):
                model_plan = remote_plan
            else:
                logger.warning("remote planner returned error, falling back to local runner")
        except Exception as exc:
            logger.error("remote planner call failed: %s", exc)

    if model_plan is None:
        model_plan = _call_model(prompt)

    if model_plan is None:
        used_fallback = True
        raw_plan = fallback_plan(retrieval_snippets, state_snapshot, user_query)
    else:
        raw_plan = model_plan

    try:
        _validate_with_schema(raw_plan)
    except Exception as exc:
        logger.error("plan validation failed: %s", exc)
        used_fallback = True
        raw_plan = fallback_plan(retrieval_snippets, state_snapshot, user_query)
        try:
            _validate_with_schema(raw_plan)
        except Exception as fallback_exc:
            logger.error("fallback validation failed: %s", fallback_exc)
            failure = _validation_failure_response(user_query)
            try:
                log_event({"event": "planner_output", "planner_output_hash": _hash_plan_output(failure)})
            except Exception:
                pass
            return failure

    if not used_fallback:
        confidence = float(raw_plan.get("confidence", 0.0) or 0.0)
        if confidence < 0.5:
            logger.warning("low confidence %.3f; using fallback", confidence)
            raw_plan = fallback_plan(retrieval_snippets, state_snapshot, user_query)
            try:
                _validate_with_schema(raw_plan)
            except Exception as exc:
                logger.error("fallback validation failed: %s", exc)
                failure = _validation_failure_response(user_query)
                try:
                    log_event({"event": "planner_output", "planner_output_hash": _hash_plan_output(failure)})
                except Exception:
                    pass
                return failure

    plan_obj = Plan.model_validate(raw_plan)
    try:
        log_event({"event": "planner_output", "planner_output_hash": _hash_plan_output(plan_obj)})
    except Exception:
        pass
    return plan_obj


'''

patched = text[:start] + replacement + text[end:]
target.write_text(patched, encoding="utf-8")
PY

mkdir -p "${ROOT}/reports"
if ! diff -u "${backup}" "${TARGET}" > "${REPORT}"; then
  status=$?
  if [[ $status -ne 1 ]]; then
    echo "diff failed (exit ${status})" >&2
    exit $status
  fi
fi

echo "Backup created at ${backup}"
echo "Patched planner/runner.py for USE_REMOTE_MODEL remote adapter switch."
echo "Diff written to ${REPORT}"
echo "No commit performed; apply manually if desired."
