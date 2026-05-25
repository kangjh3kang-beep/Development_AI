# v53 Phase 12 update: cutover checklist automation

Date: 2026-03-27
Stage: 59
Status: Completed

## Delivered

### Cutover checklist generation

- Added `scripts/release/cutover_checklist.py`
- Added `scripts/release/generate_cutover_checklist.py`
- The checklist now records:
  - overall cutover status
  - blocking items
  - per-gate checklist items for preflight, build, rollout, smoke, observability, image refs, and evidence completeness

### Workflow integration

- Updated `.github/workflows/deploy-staging.yml` to generate:
  - `cutover-checklist.md`
  - `cutover-checklist.json`
- Updated `.github/workflows/deploy-prod.yml` with the same checklist artifact flow

### Release contract hardening

- Extended `scripts/release/release_hardening.py` to require:
  - checklist-generation wiring in both deploy workflows
  - GitHub release environment secret reference coverage in `.env.example`
- Extended `.env.example` with the staging and production GitHub environment secret contract
- Extended `scripts/test/verify_system.sh` with checklist CLI validation and workflow wiring checks

### Regression and gate repair

- Extended `tests/unit/test_release_hardening_scripts.py` with cutover checklist coverage
- Updated `scripts/release/__init__.py` exports for the new release helpers
- Restored the `packages/schemas/events.py` UTC import contract so the root pytest suite stays green under the stricter gate run

## Quality gates

- `pnpm test:run` -> `106 passed`
- `pnpm type-check` -> `passed`
- `pnpm lint` -> `passed`
- `pnpm e2e:run` -> `12 passed`
- `.venv/bin/python -m pytest -q` -> `881 passed, 31 skipped, 1 warning`
- `bash scripts/test/verify_system.sh` -> `PASS 70 / FAIL 0 / WARN 0`

## Residual note

- The new checklist artifact is generated automatically by the deploy workflows, but a real cutover packet will only exist after GitHub runs the staging or production workflow with real environment secrets and cluster access.

## Next phase

The next priority after `Phase v53.12` is the first live staging rehearsal:

- inject staging environment secrets
- execute the staging deploy workflow with `workflow_dispatch`
- review `release-report` and `cutover-checklist` artifacts together
- collect operator signoff from the generated packet
- make the production cutover decision from the rehearsal evidence
