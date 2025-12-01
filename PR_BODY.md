# Harden pipeline runner and E2E coverage

## Summary
- add expanded E2E fixtures/cases and hardened pipeline runner with planner->executor mapping and exec gating
- integrate flaky test harness plus CI gating for dry-run vs allow-exec and dataset logging improvements
- enrich training dataset builder with before/after diffs for executor modifications

## Checklist
- [ ] python planner/validate_schema.py tests/e2e/cases/case*.json
- [ ] python tests/utils/flaky_runner.py pytest tests/e2e -q
- [ ] python tools/train/log_to_dataset.py

## Suggested reviewers
- @team-lead
- @infra-owner

## Merge notes
- Merge to protected branches only after verifying CI once with `ALLOW_EXEC_IN_CI=true` to exercise allow-exec gating.
