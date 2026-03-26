# v53 Phase 10 plan: observability rehearsal readiness

Date: 2026-03-27
Stage target: 57
Status: Completed

## Goal

Prepare the first live staging release rehearsal by making observability validation executable and by exposing manual deployment entry points in the release workflows.

## Scope

### Manual rehearsal entry points

- add `workflow_dispatch` to the staging and production deploy workflows
- keep the existing push and release triggers intact
- preserve the explicit release preflight, image pinning, and post-deploy smoke sequence

### Observability smoke validation

- add a reusable observability smoke helper that verifies:
  - Prometheus readiness and query API
  - Alertmanager status and receiver registration
  - Grafana health and dashboard search
- wire the helper into deploy workflows as an optional post-deploy step that activates when observability URLs are configured

### Regression and local validation

- add unit tests for the observability smoke helper
- extend `verify_system.sh` with observability CLI validation
- extend release asset validation to require the new workflow-dispatch and observability contracts

## Exit criteria

- deploy workflows can be started manually for staging rehearsal
- observability smoke validation is executable as code rather than a manual checklist only
- local quality gates stay green after the new rehearsal surface is added
