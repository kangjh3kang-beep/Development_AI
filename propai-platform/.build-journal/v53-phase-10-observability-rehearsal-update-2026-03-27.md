# v53 Phase 10 update: observability rehearsal readiness

Date: 2026-03-27
Stage: 57
Status: Completed

## Delivered

### Manual release rehearsal entry points

- Added `workflow_dispatch` support to:
  - `.github/workflows/deploy-staging.yml`
  - `.github/workflows/deploy-prod.yml`
- Kept the existing automated triggers in place, so manual rehearsal and normal release flow now share the same pipeline contract

### Observability smoke gate

- Added `scripts/release/run_observability_smoke.py`
- Extended `scripts/release/release_hardening.py` with `run_observability_smoke(...)`
- Wired optional post-deploy observability smoke steps into both deploy workflows using:
  - Prometheus URL
  - Alertmanager URL
  - Grafana URL
  - optional Grafana API key
- Extended `.env.example` with the staging and production observability variables for rehearsal setup

### Validation and regression coverage

- Extended `scripts/release/validate_release_assets.py` and the underlying asset validator to require:
  - `workflow_dispatch` on release workflows
  - observability smoke wiring
- Extended `tests/unit/test_release_hardening_scripts.py` with observability smoke coverage
- Extended `scripts/test/verify_system.sh` with observability smoke CLI validation

## Quality gates

- `pnpm test:run` -> `106 passed`
- `pnpm type-check` -> `passed`
- `pnpm lint` -> `passed`
- `pnpm e2e:run` -> `12 passed`
- `.venv/bin/python -m pytest -q` -> `877 passed, 31 skipped, 1 warning`
- `bash scripts/test/verify_system.sh` -> `PASS 68 / FAIL 0 / WARN 0`

## Residual note

- Observability smoke now exists as executable code, but it still needs real staging URLs and credentials in GitHub environments before it can run against live infrastructure.
- The non-blocking Next.js workspace-root warning during Playwright boot remains environmental noise and does not affect gate status.

## Next phase

The next priority after `Phase v53.10` is the actual staging rehearsal:

- inject staging release and observability secrets into GitHub environments
- launch the staging deploy workflow manually with `workflow_dispatch`
- capture smoke and observability evidence from the live rollout
- update the cutover checklist with the staging rehearsal result
