# v53 Phase 8 plan: deployment hardening

Date: 2026-03-26
Stage target: 55
Status: Completed

## Goal

Turn the release-candidate deployment path into an enforceable gate by validating release secrets before rollout and running a richer post-deploy smoke chain after rollout.

## Scope

### Release preflight

- add a reusable release environment validator for `staging` and `production`
- standardize deploy-time env names for kubeconfig, API URL, web URL, and smoke token
- fail early on missing or placeholder secrets instead of discovering them after rollout starts

### Post-deploy smoke

- replace the shallow curl health check with a scripted smoke chain:
  - `/health`
  - `/api/v1/auth/me`
  - `/api/v1/system/version`
  - `/api/v1/system/health/full`
  - `/api/v1/dashboard/stats`
  - key live web routes
- normalize API and web base URLs so the gate tolerates `/api/v1`, `/api/latest`, and locale suffix inputs

### Workflow and system verification

- wire the new scripts into `deploy-staging.yml` and `deploy-prod.yml`
- add release-automation checks to `scripts/test/verify_system.sh`
- add unit tests for the validator and smoke logic

## Exit criteria

- staging and production deploy workflows both fail fast on bad release contracts
- deploy workflows both run scripted post-deploy smoke validation instead of a single curl
- `verify_system.sh` validates the release automation surface
- full quality gates remain green after the deployment changes
