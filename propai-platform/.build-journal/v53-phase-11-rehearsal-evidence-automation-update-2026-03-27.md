# v53 Phase 11 update: rehearsal evidence automation

Date: 2026-03-27
Stage: 58
Status: Completed

## Delivered

### Evidence report generation

- Added `scripts/release/release_report.py`
- Added `scripts/release/generate_release_report.py`
- The report now records:
  - workflow metadata
  - step outcomes
  - image refs
  - artifact inventory
  - missing expected artifacts
  - release recommendation
- Markdown output is also appended to `GITHUB_STEP_SUMMARY` when available

### Workflow artifact capture

- Updated `.github/workflows/deploy-staging.yml` to:
  - initialize a release artifact directory
  - capture image refs
  - tee rollout and smoke outputs into files
  - capture `kubectl` overview, pods, and event evidence
  - generate a release report in an `always()` step
  - upload the final evidence bundle as an artifact
- Updated `.github/workflows/deploy-prod.yml` with the same evidence automation flow

### Validation and regression

- Extended `scripts/release/release_hardening.py` asset validation to require:
  - report generation wiring
  - artifact upload wiring
- Extended `tests/unit/test_release_hardening_scripts.py` with release evidence report coverage
- Extended `scripts/test/verify_system.sh` with release report CLI validation

## Quality gates

- `pnpm test:run` -> `106 passed`
- `pnpm type-check` -> `passed`
- `pnpm lint` -> `passed`
- `pnpm e2e:run` -> `12 passed`
- `.venv/bin/python -m pytest -q` -> `879 passed, 31 skipped, 1 warning`
- `bash scripts/test/verify_system.sh` -> `PASS 69 / FAIL 0 / WARN 0`

## Residual note

- The deploy workflows are now ready to emit evidence, but the actual evidence bundle will only be produced when the staging or production workflow runs in GitHub with real environment secrets and cluster access.

## Next phase

The next priority after `Phase v53.11` is unchanged:

- inject staging environment secrets
- execute the staging deploy workflow manually
- review the generated evidence artifact and cutover recommendation
- decide whether the system is ready for production cutover
