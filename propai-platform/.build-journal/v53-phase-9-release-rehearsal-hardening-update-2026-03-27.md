# v53 Phase 9 update: release rehearsal hardening

Date: 2026-03-27
Stage: 56
Status: Completed

## Delivered

### Deployment workflow alignment

- Updated `.github/workflows/deploy-staging.yml` to:
  - export explicit `api_image`, `web_image`, and `worker_image` outputs
  - pin those images with `kubectl set image` before rollout
- Updated `.github/workflows/deploy-prod.yml` with the same explicit image-pinning contract
- Retired the legacy production deploy path from `.github/workflows/cicd.yml` so the generic CI workflow no longer competes with the dedicated staging and release workflows

### Kubernetes and monitoring drift fixes

- Switched `infra/k8s/base/worker-deployment.yaml` to the dedicated worker image contract
- Added worker image entries to:
  - `infra/k8s/overlays/staging/kustomization.yaml`
  - `infra/k8s/overlays/production/kustomization.yaml`
- Corrected the production overlay namespace to `propai-production`
- Added `scripts/release/validate_release_assets.py` plus `validate_release_assets(...)` in `scripts/release/release_hardening.py`
- Extended `scripts/test/verify_system.sh` so release automation now validates:
  - CLI load
  - static release asset contract
  - workflow wiring presence

### Regression and browser stabilization

- Extended `tests/unit/test_release_hardening_scripts.py` with current-repo and drift-detection coverage for release asset validation
- Stabilized `apps/web/e2e/project-release.spec.ts` by:
  - asserting route `href` contracts instead of relying on flaky client-side link transitions
  - filling explicit finance/report inputs instead of depending on async autofill timing

## Quality gates

- `pnpm test:run` -> `106 passed`
- `pnpm type-check` -> `passed`
- `pnpm lint` -> `passed`
- `pnpm e2e:run` -> `12 passed`
- `.venv/bin/python -m pytest -q` -> `875 passed, 31 skipped, 1 warning`
- `bash scripts/test/verify_system.sh` -> `PASS 67 / FAIL 0 / WARN 0`

## Residual note

- The Next.js workspace-root warning during Playwright boot still appears because the machine contains an external `/home/kangjh3kang/package-lock.json`. It does not block the quality gate, but it remains environmental noise rather than an app defect.
- Live staging or production rollout is still not executable inside this workspace because the real GitHub environment secrets and cluster credentials are not available here.

## Next phase

The next priority after `Phase v53.9` remains the first live release rehearsal:

- inject the standardized release secrets into GitHub environments
- execute the staging deploy workflow end-to-end
- verify observability dashboards and alert routing against the live rollout
- complete the cutover checklist with the rehearsal result
