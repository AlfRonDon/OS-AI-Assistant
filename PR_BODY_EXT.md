Title: e2e: pipeline conductor + hardened tests + CI gating + expected-fail handling

Summary:
- Added PR enhancements and small behavior changes:
  1. PR-ready branch body + suggested reviewers and checklist.
  2. pipeline_runner: add handling for plan meta 'should_fail' as an expected failure flag (non-fatal under explicit flag).
  3. Add --dump-plan-only CLI option to pipeline_runner for plan inspection without execution.
  4. Provide quick parse of case7 repro logs (last 80 lines) and save to reports for triage.
  5. Attempt to create a PR via GitHub CLI (if available).

Files created/modified by this automation:
- PR_BODY_EXT.md (this file)
- pipeline_runner.py (patched for expected-fail handling and --dump-plan-only)
- reports/repro-case7-last80-<ts>.log (if case7 log exists)
- logs and command outputs saved to reports/codex-ops-<ts>.log

Checklist for reviewers:
- [ ] Confirm `pipeline_runner.py` changes are acceptable — especially the 'should_fail' handling semantics.
- [ ] Confirm CI gating for allow-exec remains conservative (ALLOW_EXEC_IN_CI default false).
- [ ] Review new --dump-plan-only behavior and ensure no secret leakage in plans.
- [ ] Verify flaky runner behavior in CI (records flakes into reports/flaky.json).

Suggested reviewers:
- @team-lead
- @infra-owner
- @devops

Merge notes:
- Merge into main only after at least one CI run with ALLOW_EXEC_IN_CI=false and verify pipeline logs. For protected branch full-exec CI run, set ALLOW_EXEC_IN_CI=true once and confirm results.
