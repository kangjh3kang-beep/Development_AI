# v53 Phase 9 plan: release rehearsal hardening

Date: 2026-03-27
Stage target: 56
Status: Completed

## Goal

Remove the remaining release-automation drift before the first live staging rehearsal by aligning deployment image pinning, Kubernetes overlays, monitoring assets, and browser release flows.

## Scope

### Deployment drift removal

- pin the built API, web, and worker images into staging and production deploy workflows before rollout
- remove the legacy production deploy path from the generic CI workflow
- align worker deployment manifests with the dedicated worker image contract
- fix the production namespace drift between overlays and deploy workflows

### Rehearsal asset validation

- add a static release asset validator for:
  - deploy workflow contracts
  - legacy deploy removal
  - k8s namespace and worker-image alignment
  - monitoring alerts and alertmanager webhook routing
  - Grafana dashboard asset presence
- add regression coverage and wire the validator into `verify_system.sh`

### Browser cutover stabilization

- remove flaky route-click assumptions from the project release Playwright spec
- bind the release browser suite to route contracts and explicit input state instead of client-side autofill timing

## Exit criteria

- staging and production deploy workflows both pin the exact image references built in the pipeline
- the generic CI workflow no longer performs an implicit production deploy
- static release asset validation passes locally and inside system verification
- Playwright release cutover returns to a stable green state after the rehearsal hardening
