# v53 Phase 8 update: deployment hardening

Date: 2026-03-26
Stage: 55
Status: Completed

## Delivered

### Release preflight and smoke scripts

- Added testable release automation helpers:
  - `scripts/release/release_hardening.py`
  - `scripts/release/validate_release_env.py`
  - `scripts/release/run_release_smoke.py`
- Added package entrypoints so the release helpers can be imported by pytest:
  - `scripts/__init__.py`
  - `scripts/release/__init__.py`
- Added regression coverage in `tests/unit/test_release_hardening_scripts.py` for:
  - staging contract acceptance
  - production contract rejection on bad secrets or URLs
  - URL normalization
  - smoke success and unhealthy failure cases

### Deployment workflow hardening

- Updated `.github/workflows/deploy-staging.yml` with:
  - dedicated `preflight` job
  - release contract validation
  - raw/base64 kubeconfig handling
  - worker rollout wait
  - post-deploy smoke execution
- Updated `.github/workflows/deploy-prod.yml` with the same hardening pattern and production-specific secret requirements
- Fixed the old shallow health check path by moving release validation onto the actual `/health` plus authenticated system/dashboard endpoints

### Quality-gate and environment contract alignment

- Extended `scripts/test/verify_system.sh` with release automation checks:
  - validator CLI load
  - smoke CLI load
  - workflow wiring presence
- Documented optional release smoke variables in `.env.example`

## Quality gates

- `pnpm test:run` -> `106 passed`
- `pnpm type-check` -> `passed`
- `pnpm lint` -> `passed`
- `pnpm e2e:run` -> `12 passed`
- `.venv/bin/python -m pytest -q` -> `873 passed, 31 skipped, 1 warning`
- `bash scripts/test/verify_system.sh` -> `PASS 66 / FAIL 0 / WARN 0`

## Residual note

- This phase hardens the deployment automation surface, but it does not execute a live staging or production deployment inside the workspace because real GitHub secrets and cluster access are not available here.

## Next phase

The next priority after `Phase v53.8` is live release rehearsal:

- populate the standardized release secrets in GitHub environments
- run a staging deployment with the new preflight and smoke gates
- verify observability dashboards and alert routing against the live rollout
- finalize release notes and the cutover checklist
